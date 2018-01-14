import numpy as np
import pandas as pd
from PyQt5.QtWidgets import QWidget, QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QVBoxLayout, \
    QHBoxLayout, QPushButton, QLabel, QLineEdit, QComboBox, QApplication, QHeaderView, QDateTimeEdit, QDialog
from PyQt5.Qt import QThread, pyqtSignal, Qt, QRegExpValidator, QRegExp, QDate, QSize
import sys
import os
import requests
import json
import time
import re

PATH = sys.argv[0][:sys.argv[0].rfind(os.sep) + 1] if os.sep in sys.argv[0] else ''
LogFile = 'my_logs.csv'
if LogFile not in os.listdir(PATH):
    pd.DataFrame([], columns='日期,账户,类型,金额,关联,备注'.split(',')).to_csv(PATH + LogFile, index=False)
InvestsFile = 'my_invests.csv'
if InvestsFile not in os.listdir(PATH):
    pd.DataFrame([], columns='项目,代码,名称,持有份额,持仓成本,投入资本,当前价格,当前市值,累计盈亏,收益率'.split(',')) \
        .to_csv(PATH + InvestsFile, index=False)
TOPLEVEL = '所有账户'
SUBLEVEL = ('持有', '待收', '待还', '投资')
INVESTS = ('货币', '基金', '股票')
TheLogTypes = ('收入', '支出', '调整', '转出', '借入', '还款', '借出', '收回', '投资', '赎回')


class Pricer(QThread):
    price_sender = pyqtSignal(pd.DataFrame)
    prices = pd.DataFrame([], columns=['名称', '当前价格'])

    @staticmethod
    def page_getter(url, params=None, timeout=20):
        while True:
            try:
                page = requests.get(url, params=params, timeout=timeout)
                if page.text:
                    return page.text
            except requests.exceptions.RequestException as err:
                print('[{}] An error from function: [page_getter]; error message: {}'
                      .format(pd.datetime.now().strftime('%h:%m:%s'), err))

    def run(self):
        while True:
            self.currency()
            self.funds()
            self.stocks()
            self.price_sender.emit(self.prices)
            self.prices = pd.DataFrame([], columns=['名称', '当前价格'])
            time.sleep(60 * 5)

    def currency(self):
        try:
            # page = json.loads(self.page_getter('https://blockchain.info/ticker'))
            # price1 = page['CNY']['15m']
            page = json.loads(self.page_getter('https://localbitcoins.com/buy-bitcoins-online/cny/.json'))
            price = float(page['data']['ad_list'][0]['data']['temp_price'])
            self.prices = self.prices.append(pd.Series({'项目': '货币', '名称': 'BTC', '当前价格': price}, name='BTC'))
            cryptos = MainWin.invests[MainWin.invests['项目'] == '货币'].index.tolist()
            cryptos.remove('BTC')
            url = 'https://min-api.cryptocompare.com/data/price?fsym=BTC&tsyms={}'.format(','.join(cryptos))
            page = json.loads(self.page_getter(url))
            for each in page.keys():
                self.prices = self.prices.append(pd.Series({'项目': '货币', '名称': each,
                                                            '当前价格': price / page[each]}, name=each))
        except json.decoder.JSONDecodeError:
            self.currency()

    def funds(self):
        funds = MainWin.invests[MainWin.invests['项目'] == '基金']
        if len(funds.index):
            fcodes = funds.index.tolist()
            url = 'https://fundmobapi.eastmoney.com/FundMApi/FundRankNewList.ashx?'
            data = {'pagesize': 10000, 'deviceid': 'Wap', 'plat': 'Wap', 'product': 'EFund', 'version': '2.0.0'}
            data = json.loads(self.page_getter(url, params=data))['Datas']
            f_list = [pd.Series({'项目': '基金', '名称': x['SHORTNAME'], '当前价格': x['DWJZ']}, name=x['FCODE']) for x in data]
            f_df = pd.DataFrame(f_list)
            self.prices = pd.concat([self.prices, f_df.loc[fcodes]])

    def stocks(self):
        def cook_code(scode):
            if len(scode) == 5:
                return 'hk' + scode
            elif '60' in scode[:2]:
                return 's_sh' + scode
            else:
                return 's_sz' + scode

        def cook_page(page_text):
            ret = {}
            _stocks = re.findall('_?s?_\w{2}(\d{5,6})="(.+)";', page_text)
            for row in _stocks:
                code, _data = row[0], row[1].split(',')
                name, price = _data[0], _data[1]
                ret[code] = pd.Series({'项目': '股票', '名称': name, '当前价格': float(price)})
            return pd.DataFrame(ret).T

        url = 'http://hq.sinajs.cn/list='
        stocks = MainWin.invests[MainWin.invests['项目'] == '股票']
        if len(stocks.index):
            scodes = stocks.index.tolist()
            url += ','.join([cook_code(x) for x in scodes])
            self.prices = pd.concat([self.prices, cook_page(self.page_getter(url))])


class MyTableItem(QTableWidgetItem):
    def __lt__(self, other):
        if isinstance(other, QTableWidgetItem):
            try:
                my_value = float(re.search(r'([+|-]?\d+\.\d+|0)', self.text()).group(1))
                other_value = float(re.search(r'([+|-]?\d+\.\d+|0)', other.text()).group(1))
                return my_value < other_value
            except (AttributeError, TypeError):
                return super(MyTableItem, self).__lt__(other)


class MainWin(QWidget):
    logs = pd.read_csv(PATH + LogFile, converters={'日期': pd.to_datetime})
    logs.set_index('日期', inplace=True)
    invests = pd.read_csv(PATH + InvestsFile, index_col='代码')

    def __init__(self, parent=None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.setWindowTitle('羊家记账薄')
        self.setMinimumSize(QSize(1600, 800))
        # this variable is used to hold all tree-items within the left-tree
        # in order to easily modify balances of each items.
        self.myAccountsItems = {}
        self.grouped_lv1 = {}
        self.grouped_lv2 = {}
        self.prices = None
        self.ThePricer = Pricer()
        self.ThePricer.price_sender.connect(self.price_received)
        self.ThePricer.start()

        mainLayout = QVBoxLayout()
        topLayout = QHBoxLayout()
        saveButton = QPushButton('保存')
        saveButton.setFixedWidth(50)
        saveButton.clicked.connect(self.save_data)
        topLayout.addWidget(saveButton)
        self.infoDisplayer = QLabel()
        topLayout.addWidget(self.infoDisplayer, alignment=Qt.AlignCenter)
        self.typeFilterBox = QComboBox()
        self.typeFilterBox.setMaximumWidth(150)
        self.typeFilterBox.addItems(('全部',) + TheLogTypes)
        self.typeFilterBox.currentIndexChanged.connect(self.display_table)
        topLayout.addWidget(self.typeFilterBox)
        mainLayout.addLayout(topLayout)

        downlayout = QHBoxLayout()
        self.leftTree = QTreeWidget()
        self.leftTree.setColumnCount(3)
        self.leftTree.setHeaderHidden(True)
        self.leftTree.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.leftTree.setFixedWidth(350)
        self.leftTree.clicked.connect(self.display_table)

        self.rightTable = QTableWidget()
        self.rightTable.setSelectionBehavior(QTableWidget.SelectRows)
        self.rightTable.setEditTriggers(QTableWidget.NoEditTriggers)
        self.rightTable.setSelectionMode(QTableWidget.SingleSelection)
        self.rightTable.setSortingEnabled(True)
        self.rightTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.rightTable.doubleClicked.connect(self.doubleclicked)
        downlayout.addWidget(self.leftTree, alignment=Qt.AlignJustify)
        downlayout.addWidget(self.rightTable)

        bottonlayout = QHBoxLayout()

        self.record_date_line = QDateTimeEdit()
        self.record_date_line.setDisplayFormat('yyyy-MM-dd')
        self.record_date_line.setDate(QDate(pd.datetime.now().year, pd.datetime.now().month, pd.datetime.now().day))
        self.record_date_line.setFixedWidth(120)
        self.accounts_name_box = QComboBox()
        self.accounts_name_box.currentTextChanged.connect(self.acc_name_changed)
        self.new_account_line = QLineEdit()
        self.new_account_line.setVisible(False)
        self.new_account_line.setFixedWidth(100)
        self.record_type_box = QComboBox()
        self.record_type_box.addItems(TheLogTypes)
        self.record_type_box.currentIndexChanged.connect(self.record_type_changed)
        self.account_ralative_box = QComboBox()
        self.account_ralative_box.currentTextChanged.connect(self.acc_relative_changed)
        self.account_ralative_box.setVisible(False)
        self.new_account_relative_line = QLineEdit()
        self.new_account_relative_line.setVisible(False)
        self.new_account_relative_line.setFixedWidth(100)
        self.costs_line = QLineEdit()
        self.costs_line.setValidator(QRegExpValidator(QRegExp(r'[0-9]+\.?[0-9]+')))
        self.costs_line.setFixedWidth(100)
        self.notes_line = QLineEdit()
        self.okButton = QPushButton('确认')
        self.okButton.setFixedWidth(40)
        self.okButton.clicked.connect(self.ok_pressed)
        self.deleteButton = QPushButton('删除')
        self.deleteButton.setFixedWidth(40)
        self.deleteButton.clicked.connect(self.del_pressed)
        bottonlayout.addWidget(QLabel('日期'))
        bottonlayout.addWidget(self.record_date_line)
        bottonlayout.addWidget(self.accounts_name_box)
        bottonlayout.addWidget(self.new_account_line)
        bottonlayout.addWidget(self.record_type_box)
        bottonlayout.addWidget(QLabel('金额'))
        bottonlayout.addWidget(self.costs_line)
        bottonlayout.addWidget(self.account_ralative_box)
        bottonlayout.addWidget(self.new_account_relative_line)
        bottonlayout.addWidget(QLabel('备注'))
        bottonlayout.addWidget(self.notes_line)
        bottonlayout.addWidget(self.okButton)
        bottonlayout.addWidget(self.deleteButton)

        mainLayout.addLayout(downlayout)
        mainLayout.addLayout(bottonlayout)

        investsLayout = QHBoxLayout()
        investsLayout.addStretch(40)
        investsLayout.addWidget(QLabel('投资类型'))
        self.invests_types_combobox = QComboBox()
        self.invests_types_combobox.addItems(INVESTS)
        investsLayout.addWidget(self.invests_types_combobox)
        investsLayout.addWidget(QLabel('代码'))
        self.invests_codes_line = QLineEdit()
        investsLayout.addWidget(self.invests_codes_line)
        investsLayout.addWidget(QLabel('份额'))
        self.invests_shares_line = QLineEdit()
        self.invests_shares_line.setValidator(QRegExpValidator(QRegExp(r'[0-9]+\.?[0-9]+')))
        investsLayout.addWidget(self.invests_shares_line)
        investsLayout.addWidget(QLabel('单价'))
        self.invests_price_line = QLineEdit()
        self.invests_price_line.setValidator(QRegExpValidator(QRegExp(r'[0-9]+\.?[0-9]+')))
        investsLayout.addWidget(self.invests_price_line)
        investsLayout.addWidget(QLabel('费率(%)'))
        self.invests_fee_line = QLineEdit()
        self.invests_fee_line.setText('0')
        self.invests_fee_line.setValidator(QRegExpValidator(QRegExp(r'[0-9]+\.?[0-9]+')))
        investsLayout.addWidget(self.invests_fee_line)
        mainLayout.addLayout(investsLayout)

        investConvertLayout = QHBoxLayout()
        investConvertLayout.addStretch(100)
        self.convert_ok_button = QPushButton('投资转换')
        self.convert_ok_button.clicked.connect(self.convert_investments)
        investConvertLayout.addWidget(self.convert_ok_button)
        investConvertLayout.addWidget(QLabel('从代码：'))
        self.convert_left_code_line = QLineEdit()
        investConvertLayout.addWidget(self.convert_left_code_line)
        investConvertLayout.addWidget(QLabel('量：'))
        self.convert_left_amount_line = QLineEdit()
        investConvertLayout.addWidget(self.convert_left_amount_line)
        investConvertLayout.addWidget(QLabel('到代码：'))
        self.convert_right_code_line = QLineEdit()
        investConvertLayout.addWidget(self.convert_right_code_line)
        investConvertLayout.addWidget(QLabel('量：'))
        self.convert_right_amount_line = QLineEdit()
        investConvertLayout.addWidget(self.convert_right_amount_line)
        mainLayout.addLayout(investConvertLayout)

        self.setLayout(mainLayout)
        self.rebox()
        self.display_tree()

    @staticmethod
    def save_data():
        try:
            os.mkdir(PATH + 'backup')
        except:
            pass
        old_logs = PATH + 'backup/' + pd.datetime.now().strftime('%Y%m%d%H%M%S') + '_bak_' + LogFile
        old_invests = PATH + 'backup/' + pd.datetime.now().strftime('%Y%m%d%H%M%S') + '_bak_' + InvestsFile
        MainWin.logs.to_csv(old_logs)
        MainWin.invests.to_csv(old_invests)
        MainWin.logs.to_csv(PATH + LogFile)
        MainWin.invests.to_csv(PATH + InvestsFile)

    def rebox(self):
        self.accounts_name_box.clear()
        self.account_ralative_box.clear()
        acc1 = sorted(MainWin.logs['账户'].unique().tolist())
        acc2 = sorted([x for x in MainWin.logs['关联'].unique().tolist() if isinstance(x, str) and x not in acc1])
        acc = acc1 + acc2
        acc.append('新增')
        self.accounts_name_box.addItems(acc)
        self.account_ralative_box.addItems(acc)

    def record_type_changed(self, index):
        if index in (3, 4, 5, 6, 7):
            self.account_ralative_box.setVisible(True)
        else:
            self.account_ralative_box.setVisible(False)

    def acc_name_changed(self, text):
        if text in '新增':
            self.new_account_line.setVisible(True)
        else:
            self.new_account_line.setVisible(False)

    def acc_relative_changed(self, text):
        if text in '新增':
            self.new_account_relative_line.setVisible(True)
        else:
            self.new_account_relative_line.setVisible(False)

    def price_received(self, frame):
        MainWin.invests.update(frame)
        self.calculate_invests()
        self.record_date_line.setDate(QDate(pd.datetime.now().year, pd.datetime.now().month, pd.datetime.now().day))

    def calculate_invests(self):
        MainWin.invests.drop(MainWin.invests[(MainWin.invests['累计盈亏'] == 0) & (MainWin.invests['持有份额'] == 0)].index,
                             inplace=True)
        MainWin.invests.loc[:, '当前价格'] = pd.to_numeric(MainWin.invests['当前价格'])
        MainWin.invests.loc[:, '当前市值'] = MainWin.invests['当前价格'] * MainWin.invests['持有份额']
        MainWin.invests.loc[:, '累计盈亏'] = MainWin.invests['当前市值'] - MainWin.invests['投入资本']
        MainWin.invests.loc[:, '收益率'] = MainWin.invests['累计盈亏'] / MainWin.invests['投入资本']
        MainWin.invests.loc[:, '成本权重'] = MainWin.invests['投入资本'] / MainWin.invests['投入资本'].sum()
        MainWin.invests.loc[:, '摊薄收益率'] = MainWin.invests['成本权重'] * MainWin.invests['收益率']
        self.display_tree()

    def group_logs(self):
        def neg_func(x):
            try:
                return -x
            except TypeError:
                return x

        self.grouped_lv2[SUBLEVEL[0]] = {each[0]: each[1] for each in MainWin.logs.groupby('账户')}
        for each in MainWin.logs.groupby('关联'):
            if each[0] in self.grouped_lv2[SUBLEVEL[0]]:
                copied = each[1].copy()
                copied.loc[:, '金额'] = -copied['金额']
                self.grouped_lv2[SUBLEVEL[0]][each[0]] = pd.concat([self.grouped_lv2[SUBLEVEL[0]][each[0]], copied])
        self.grouped_lv1[SUBLEVEL[0]] = pd.concat(self.grouped_lv2[SUBLEVEL[0]].values())
        self.grouped_lv2[SUBLEVEL[1]] = {each[0]: each[1].apply(neg_func) for each in
                                         MainWin.logs[MainWin.logs['类型'].str.contains(r'借出|收回')].groupby('关联')}
        self.grouped_lv1[SUBLEVEL[1]] = pd.concat(self.grouped_lv2[SUBLEVEL[1]].values())
        self.grouped_lv2[SUBLEVEL[2]] = {each[0]: each[1].apply(neg_func) for each in
                                         MainWin.logs[MainWin.logs['类型'].str.contains(r'借入|还款')].groupby('关联')}
        self.grouped_lv1[SUBLEVEL[2]] = pd.concat(self.grouped_lv2[SUBLEVEL[2]].values())

    def display_tree(self):
        MainWin.logs = MainWin.logs.reindex(columns='账户,类型,金额,关联,备注'.split(','))
        MainWin.invests = MainWin.invests.reindex(columns='项目,名称,收益率,累计盈亏,当前价格,持仓成本,'
                                                          '当前市值,投入资本,持有份额,成本权重,摊薄收益率'.split(','))
        self.group_logs()

        # def total_val():
        #     belongs = 0
        #     holding = 0
        #     for each in self.grouped:
        #         belongs += self.grouped[each]['value']
        #         holding += self.grouped[each]['value'] if self.grouped[each]['value'] > 0 else 0
        #     belongs += MainWin.invests['当前市值'].sum()
        #     holding += MainWin.invests['当前市值'].sum()
        #     return belongs, holding
        #
        # total = total_val()
        belongs = self.grouped_lv1[SUBLEVEL[0]]['金额'].sum() + self.grouped_lv1[SUBLEVEL[1]]['金额'].sum() + \
                  self.grouped_lv1[SUBLEVEL[2]]['金额'].sum() + self.invests['当前市值'].sum()
        holding = self.grouped_lv1[SUBLEVEL[0]]['金额'].sum() + self.invests['当前市值'].sum()
        if TOPLEVEL not in self.myAccountsItems:
            item = QTreeWidgetItem()
            item.setText(0, TOPLEVEL)
            item.setText(1, '{:.2f}'.format(belongs))
            item.setText(2, '{:.2f}'.format(holding))
            self.myAccountsItems[TOPLEVEL] = item
            self.leftTree.addTopLevelItem(item)
        else:
            self.myAccountsItems[TOPLEVEL].setText(1, '{:.2f}'.format(belongs))
            self.myAccountsItems[TOPLEVEL].setText(2, '{:.2f}'.format(holding))

        for acc in self.grouped_lv1:
            remain = self.grouped_lv1[acc]['金额'].sum()
            if acc not in self.myAccountsItems:
                item = QTreeWidgetItem()
                item.setText(0, acc)
                item.setText(1, '{:.2f}'.format(remain))
                self.myAccountsItems[acc] = item
                self.myAccountsItems[TOPLEVEL].addChild(item)
            else:
                self.myAccountsItems[acc].setText(1, '{:.2f}'.format(remain))
            for sub_acc in self.grouped_lv2[acc]:
                remain = self.grouped_lv2[acc][sub_acc]['金额'].sum()
                if sub_acc not in self.myAccountsItems:
                    item = QTreeWidgetItem()
                    item.setText(0, sub_acc)
                    item.setText(1, '{:.2f}'.format(remain))
                    self.myAccountsItems[sub_acc] = item
                    self.myAccountsItems[acc].addChild(item)
                else:
                    self.myAccountsItems[sub_acc].setText(1, '{:.2f}'.format(remain))

        remain = MainWin.invests['当前市值'].sum()
        if SUBLEVEL[3] not in self.myAccountsItems:
            item = QTreeWidgetItem()
            item.setText(0, SUBLEVEL[3])
            item.setText(1, '{:.2f}'.format(remain))
            self.myAccountsItems[SUBLEVEL[3]] = item
            self.myAccountsItems[TOPLEVEL].addChild(item)
        else:
            self.myAccountsItems[SUBLEVEL[3]].setText(1, '{:.2f}'.format(remain))

        for iname, invests in MainWin.invests.groupby('项目'):
            remain = invests['当前市值'].sum()
            if iname not in self.myAccountsItems:
                item = QTreeWidgetItem()
                item.setText(0, iname)
                item.setText(1, '{:.2f}'.format(remain))
                self.myAccountsItems[iname] = item
                self.myAccountsItems[SUBLEVEL[3]].addChild(item)
            else:
                self.myAccountsItems[iname].setText(1, '{:.2f}'.format(remain))

        self.leftTree.expandAll()
        self.leftTree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.display_table()

    def display_table(self):
        def place_item():
            self.rightTable.setColumnCount(len(items2Place.columns) + 1)
            self.rightTable.setHorizontalHeaderLabels([items2Place.index.name] + list(items2Place.columns))
            self.rightTable.setRowCount(len(items2Place))
            for r_idx, row in enumerate(items2Place.index):
                text = str(row)
                titem = QTableWidgetItem(text)
                titem.setTextAlignment(Qt.AlignCenter)
                if isinstance(row, pd.datetime):
                    titem.setText(row.strftime('%Y-%m-%d'))
                    titem.setData(1000, row)
                self.rightTable.setItem(r_idx, 0, titem)
                for c_idx, data in enumerate(items2Place.loc[row]):
                    text = str(data)
                    if text in ('None', 'nan'):
                        continue
                    titem = QTableWidgetItem(text)
                    if isinstance(data, (float, int)):
                        if items2Place.loc[row].index[c_idx] in ('收益率', '成本权重', '摊薄收益率'):
                            text = '{:.2%}'.format(data)
                        else:
                            text = string_float(data)
                        titem = MyTableItem(text)
                        titem.setData(1000, data)
                    titem.setTextAlignment(Qt.AlignCenter)
                    self.rightTable.setItem(r_idx, c_idx + 1, titem)

        self.rightTable.clear()
        self.rightTable.setSortingEnabled(False)
        current_table_text = self.leftTree.currentItem().text(0) if self.leftTree.currentItem() else TOPLEVEL
        # MainWin.logs = MainWin.logs.reindex(columns=['账户', '类型', '关联', '金额', '备注'])
        # MainWin.invests = MainWin.invests.reindex(columns=['项目', '名称', '收益率', '成本权重', '摊薄收益率', '累计盈亏',
        #                                                    '当前价格', '当前市值', '投入资本', '持仓成本', '持有份额'])

        if current_table_text in TOPLEVEL:
            items2Place = MainWin.logs
            self.infoDisplayer.setText(self.account_display(current_table_text, items2Place))
        elif current_table_text in SUBLEVEL[:-1]:
            items2Place = self.grouped_lv1[current_table_text]
            if self.typeFilterBox.currentText() not in '全部':
                items2Place = items2Place[items2Place['类型'] == self.typeFilterBox.currentText()]
            self.infoDisplayer.setText(self.account_display(current_table_text, items2Place))
        elif current_table_text in SUBLEVEL[-1]:
            items2Place = MainWin.invests
            self.infoDisplayer.setText(self.invests_display(current_table_text, items2Place))
        elif current_table_text in INVESTS:
            items2Place = MainWin.invests[MainWin.invests['项目'] == current_table_text]
            self.infoDisplayer.setText(self.invests_display(current_table_text, items2Place))
        else:
            if current_table_text in self.grouped_lv2[SUBLEVEL[0]].keys():
                items2Place = self.grouped_lv2[SUBLEVEL[0]][current_table_text]
            elif current_table_text in self.grouped_lv2[SUBLEVEL[1]].keys():
                items2Place = self.grouped_lv2[SUBLEVEL[1]][current_table_text]
            elif current_table_text in self.grouped_lv2[SUBLEVEL[2]].keys():
                items2Place = self.grouped_lv2[SUBLEVEL[2]][current_table_text]
            else:
                return
            if self.typeFilterBox.currentText() not in '全部':
                items2Place = items2Place[items2Place['类型'] == self.typeFilterBox.currentText()]
            self.infoDisplayer.setText(self.account_display(current_table_text, items2Place))
        place_item()
        self.rightTable.setSortingEnabled(True)
        if current_table_text in ('投资',) + INVESTS:
            self.rightTable.sortByColumn(3, Qt.DescendingOrder)
        else:
            self.rightTable.sortByColumn(0, Qt.DescendingOrder)

    @staticmethod
    def invests_display(kw, frame_items):
        ret = '[{}]\t 成本 {:.2f} 元\t市值 {:.2f} 元\t收益 {:.2f}\t  收益率 {:.2%}'
        invested = frame_items['投入资本'].sum()
        worthy = frame_items['当前市值'].sum()
        return ret.format(kw, invested, worthy, worthy - invested, (worthy - invested) / invested)

    @staticmethod
    def account_display(kw, frame_items, rep1='净收入', rep2='净支出'):
        ret = '[{}]\t {} {:.2f} 元\t{} {:.2f} 元'
        income = frame_items[(frame_items['金额'] > 0)]['金额'].sum()
        outcome = frame_items[(frame_items['金额'] < 0)]['金额'].sum()
        return ret.format(kw, rep1, income, rep2, outcome)

    def ok_pressed(self):
        date = self.record_date_line.date()
        hour, minute, sec = pd.datetime.now().hour, pd.datetime.now().minute, pd.datetime.now().second
        date = pd.datetime(date.year(), date.month(), date.day(), hour, minute, sec)
        log_name = self.new_account_line.text() \
            if self.accounts_name_box.currentText() in '新增' else self.accounts_name_box.currentText()
        log_type = self.record_type_box.currentText()
        money = float(self.costs_line.text()) if self.costs_line.text() else 0
        log_relative = self.account_ralative_box.currentText() if self.account_ralative_box.isVisible() else None
        if log_relative and log_relative in '新增':
            log_relative = self.new_account_relative_line.text()
        notes = self.notes_line.text()
        if log_type in ('投资', '赎回'):
            inv_type = self.invests_types_combobox.currentText()
            inv_code = self.invests_codes_line.text() if self.invests_codes_line.text() else None
            if not inv_code:
                return
            inv_fee = float(self.invests_fee_line.text()) / 100 if self.invests_fee_line.text() else 0
            inv_unit_price = float(self.invests_price_line.text()) if self.invests_price_line.text() else 0
            inv_shares = float(self.invests_shares_line.text()) if self.invests_shares_line.text() else 0
            try:
                money, notes = self.invests_adding(
                    log_type, inv_code, inv_type, money, inv_fee, inv_unit_price, inv_shares)
            except Exception:
                return
        self.logs_appending(date, log_name, log_type, money, log_relative, notes)
        self.display_tree()
        self.save_data()

    def logs_appending(self, date, name, ttype, money, relative, notes):
        money = -money if ttype in ['支出', '转出', '贷款', '还款', '借出'] else money
        money = money - float(self.myAccountsItems[name].text(1)) if ttype in '调整' else money
        nframe = pd.DataFrame([{'日期': date, '账户': name, '类型': ttype, '金额': money, '关联': relative, '备注': notes}])
        nframe.set_index('日期', inplace=True)
        MainWin.logs = MainWin.logs.append(nframe)

    def invests_adding(self, ltype, code, itype, costs, fee, price, shares):
        shares = costs / price if not shares and price else shares
        price = costs / shares if not price and shares else price
        costs = shares * price if not costs else costs
        if not shares and not costs:
            raise Exception()
        # see if it has already in investment logs
        if code in MainWin.invests.index:
            if ltype in '投资':
                # counting the shares can final get after fee
                shares = shares * (1 - fee)
                MainWin.invests.loc[code, '投入资本'] += costs
                MainWin.invests.loc[code, '持有份额'] += shares
                # it has to be nagetive in order to log.
                costs = -costs
            elif ltype in '赎回':
                new_shares = MainWin.invests.loc[code, '持有份额'] - shares
                # if the given shares beyond all I have, that means sell all of them.
                if new_shares < 0:
                    new_shares = 0
                    shares = MainWin.invests.loc[code, '持有份额']
                    costs = price * shares
                MainWin.invests.loc[code, '持有份额'] = new_shares
                MainWin.invests.loc[code, '投入资本'] -= costs
                # recount how much should get back after fee
                costs = costs * (1 - fee)
            invests = MainWin.invests.loc[code, '投入资本']
            holdings = MainWin.invests.loc[code, '持有份额']
            MainWin.invests.loc[code, '持仓成本'] = invests / holdings if holdings else 0
        elif ltype in '投资':
            nframe = pd.DataFrame([{'代码': code, '项目': itype, '名称': np.nan, '持有份额': shares, '持仓成本': price,
                                    '投入资本': costs, '当前价格': np.nan, '当前市值': np.nan, '累计盈亏': np.nan, '收益率': np.nan}])
            nframe.set_index('代码', inplace=True)
            MainWin.invests = MainWin.invests.append(nframe)
            costs = -costs
        else:
            raise Exception()
        notes = '{}|{}|{}|{}'.format(itype, code, shares, fee)
        self.calculate_invests()
        return costs, notes

    def del_pressed(self):
        # see if any item is selected in tables
        item_row = self.rightTable.currentRow()
        if item_row == -1:
            return
        # investments are not allowed to delete at this moment
        ttype = self.leftTree.currentItem().text(0)
        if ttype in ('投资',) + INVESTS:
            return
        date = self.rightTable.item(item_row, 0).data(1000)
        # catch the items that need to be deleted.
        items_to_delete = MainWin.logs.loc[date]
        MainWin.logs.drop(date, inplace=True)
        # this operation is use to adjust the data in investments after the logs changed.
        if items_to_delete['类型'] in ('投资', '赎回'):
            cost = items_to_delete['金额']
            itype, code, shares, fee = items_to_delete['备注'].split('|')
            if items_to_delete['类型'] in '投资':
                MainWin.invests.loc[code, '持有份额'] -= float(shares)
                MainWin.invests.loc[code, '投入资本'] += cost
            else:
                MainWin.invests.loc[code, '持有份额'] += float(shares)
                MainWin.invests.loc[code, '投入资本'] += cost / (1 - float(fee))
            invests = MainWin.invests.loc[code, '投入资本']
            holdings = MainWin.invests.loc[code, '持有份额']
            MainWin.invests.loc[code, '持仓成本'] = invests / holdings if holdings else 0
            self.calculate_invests()
        self.display_tree()
        self.save_data()

    def doubleclicked(self, item):
        if self.leftTree.currentItem().text(0) in ('投资', '基金', '股票', '货币'):
            code = self.rightTable.item(item.row(), 0).text()
            logs = MainWin.logs[MainWin.logs['备注'].notnull()]
            logs = logs[logs['备注'].str.contains(code)]
            if not len(logs):
                return
            price = self.rightTable.item(item.row(), 5).text()
            d = DetailedWin('{} {}'.format(code, self.rightTable.item(item.row(), 2).text()),
                            logs, float(price), parent=self)
            d.show()

    def convert_investments(self):
        try:
            itype = self.invests_types_combobox.currentText()
            l_code = self.convert_left_code_line.text()
            l_amount = float(self.convert_left_amount_line.text())
            r_code = self.convert_right_code_line.text()
            r_amount = float(self.convert_right_amount_line.text())
            total_getback = l_amount * MainWin.invests.loc[l_code, '当前价格']
            if l_code and l_amount and r_code and r_amount:
                self.invests_adding('赎回', l_code, itype, total_getback, 0, 0, l_amount)
                self.invests_adding('投资', r_code, itype, total_getback, 0, 0, r_amount)
                self.display_tree()
        except:
            return


class DetailedWin(QDialog):
    def __init__(self, title, logs, price, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(800)
        mainlo = QHBoxLayout()
        table = QTableWidget()
        title = ['日期', '投入|回收', '份额', '单价成本', '当前价格', '市值', '盈亏', '收益']
        table.setColumnCount(len(title))
        table.setHorizontalHeaderLabels(title)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        remain = []
        get_back = {'q': 0, 'm': 0}
        for idx in logs.index:
            row = logs.loc[idx]
            money = -row['金额']
            _, _, quan, fee = row['备注'].split('|')
            each_cost = (money * (1 - float(fee))) / float(quan)
            if row['类型'] in '投资':
                remain.append([idx.strftime('%Y-%m-%d'), money, float(quan), each_cost])
            else:
                get_back['q'] += float(quan)
                get_back['m'] += money
        try:
            get_back['avg'] = get_back['m'] / get_back['q']
        except ZeroDivisionError:
            get_back['avg'] = 0
        frame = pd.DataFrame(remain).sort_values(3)
        for idx in frame.index:
            if get_back['q'] and get_back['m']:
                if frame.loc[idx, 2] >= get_back['q']:
                    frame.loc[idx, 2] -= get_back['q']
                    frame.loc[idx, 1] -= get_back['m']
                    break
                else:
                    money_sub = frame.loc[idx, 2] * get_back['avg']
                    get_back['q'] -= frame.loc[idx, 2]
                    get_back['m'] -= money_sub
                    frame.loc[idx, 2] = 0
                    frame.loc[idx, 1] -= money_sub
        table.setRowCount(len(frame))
        for _r, idx in enumerate(frame.index):
            row = frame.loc[idx]
            invests = row[1]
            quan = row[2]
            each_cost = row[3]
            worthy_now = float(quan) * float(price)
            earned = worthy_now - invests
            change = earned / invests
            table.setItem(_r, 0, QTableWidgetItem(row[0]))
            table.setItem(_r, 1, MyTableItem(string_float(invests)))
            table.setItem(_r, 2, MyTableItem(string_float(quan)))
            table.setItem(_r, 3, MyTableItem(string_float(each_cost)))
            table.setItem(_r, 4, MyTableItem(string_float(price)))
            table.setItem(_r, 5, MyTableItem(string_float(worthy_now)))
            table.setItem(_r, 6, MyTableItem(string_float(earned)))
            table.setItem(_r, 7, MyTableItem('{:.4%}'.format(change)))
        table.sortByColumn(0, Qt.DescendingOrder)
        mainlo.addWidget(table)
        self.setLayout(mainlo)


def string_float(values):
    return '{:.2f}'.format(values) if abs(values) > 100 else '{:.4f}'.format(values)


app = QApplication([])

win = MainWin()
win.show()

app.exec()
