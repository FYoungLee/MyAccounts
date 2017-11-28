import pandas as pd
import numpy as np
from PyQt5.QtWidgets import QWidget, QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QVBoxLayout, \
    QHBoxLayout, QPushButton, QLabel, QLineEdit, QComboBox, QMessageBox, QApplication, QHeaderView, QDateTimeEdit
from PyQt5.Qt import QThread, pyqtSignal, Qt, QRegExpValidator, QRegExp, QDate
import sys
import os
import requests
import json
import time

PATH = sys.argv[0][:sys.argv[0].rfind(os.sep) + 1] if os.sep in sys.argv[0] else ''
LogFile = 'my_logs.csv'
if LogFile not in os.listdir(PATH):
    pd.DataFrame([], columns='日期,发起账户,类型,金额,目标账户,附言,账户类型'.split(',')).to_csv(PATH + LogFile, index=False)
InvestsFile = 'my_invests.csv'
if InvestsFile not in os.listdir(PATH):
    pd.DataFrame([], columns='类型,代码,名称,持有份额,持仓成本,投入资本,当前价格,当前市值,累计盈亏,收益率'.split(','))\
        .to_csv(PATH + InvestsFile, index=False)
TOPLEVEL = '所有账户'
SUBLEVEL = ['我有的', '要还的', '欠我的']
log_types = ['收入', '支出', '调整', '转出', '贷款', '还款', '借出', '投资', '赎回']
oppo_log_types = {'转出': '转入', '贷款': '借入', '还款': '消贷', '借出': '待收'}
BitCoinAccountName = '比特币'


class Pricer(QThread):
    price_sender = pyqtSignal(dict)
    prices = {'btc': 0, 'fund': None, 'stock': {}}

    def run(self):
        while True:
            self.bitcoin()
            self.funds()
            self.stocks()
            self.price_sender.emit(self.prices)
            time.sleep(60)

    def bitcoin(self):
        try:
            page = json.loads(requests.get('https://blockchain.info/ticker', timeout=10).text)
            self.prices['btc'] = page['CNY']['15m']
        except Exception as err:
            print(err)

    def funds(self):
        url = 'https://fundmobapi.eastmoney.com/FundMApi/FundRankNewList.ashx?pagesize=10000&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0'
        try:
            data = json.loads(requests.get(url, timeout=20).text)['Datas']
            self.prices['fund'] = {x['FCODE']: (x['SHORTNAME'], x['DWJZ']) for x in data}
        except Exception as err:
            print(err)

    def stocks(self):
        for stockID in self.prices['stock']:
            pass

    def append(self, types, code):
        if types in ('fund', 'stock'):
            self.prices[types][code] = 0


class MainWin(QWidget):
    def __init__(self, parent=None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.setWindowTitle('羊家记账薄')
        self.setMinimumWidth(1280)
        # this variable is used to hold all tree-items in the left-tree to make the items easy to modify the balance.
        self.myAccountsItems = {}
        self.prices = None
        self.pricers = Pricer()
        self.pricers.price_sender.connect(self.price_received)
        self.pricers.start()
        self.logs = pd.read_csv(PATH + LogFile, converters={'日期': pd.to_datetime})
        self.invests = pd.read_csv(PATH + InvestsFile, converters={'日期': pd.to_datetime, '代码': str})

        mainLayout = QVBoxLayout()
        topLayout = QHBoxLayout()
        saveBTN = QPushButton('保存')
        saveBTN.setFixedWidth(50)
        saveBTN.clicked.connect(self.save_data)
        topLayout.addWidget(saveBTN)
        self.displayBar = QLabel()
        topLayout.addWidget(self.displayBar, alignment=Qt.AlignCenter)
        mainLayout.addLayout(topLayout)

        downlayout = QHBoxLayout()
        self.leftTree = QTreeWidget()
        self.leftTree.setColumnCount(3)
        self.leftTree.setHeaderHidden(True)
        self.leftTree.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.leftTree.setMaximumWidth(450)
        self.leftTree.itemClicked.connect(self.tree_item_clicked)
        self.init_tree()

        self.rightTable = QTableWidget()
        self.rightTable.setMinimumWidth(500)
        self.rightTable.setSelectionBehavior(QTableWidget.SelectRows)
        self.rightTable.setEditTriggers(QTableWidget.NoEditTriggers)
        self.rightTable.setSelectionMode(QTableWidget.SingleSelection)
        self.rightTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        downlayout.addWidget(self.leftTree, alignment=Qt.AlignJustify)
        downlayout.addWidget(self.rightTable)

        bottonlayout = QHBoxLayout()

        self.balnameline = QLineEdit()
        self.balnameline.setFixedWidth(80)
        self.baltypebox = QComboBox()
        self.baltypebox.setFixedWidth(65)
        self.baltypebox.addItems(SUBLEVEL)
        self.addbalbtn = QPushButton('添加')
        self.addbalbtn.setFixedWidth(40)
        self.addbalbtn.clicked.connect(self.add_accounts)
        self.delbalbtn = QPushButton('删除')
        self.delbalbtn.setFixedWidth(40)
        self.delbalbtn.clicked.connect(self.del_accounts)
        bottonlayout.addWidget(self.balnameline)
        bottonlayout.addWidget(self.baltypebox)
        bottonlayout.addWidget(self.addbalbtn)
        bottonlayout.addWidget(self.delbalbtn)
        bottonlayout.addStretch(1)

        self.record_date_line = QDateTimeEdit()
        self.record_date_line.setDisplayFormat('yyyy-MM-dd')
        self.record_date_line.setDate(QDate(pd.datetime.now().year, pd.datetime.now().month, pd.datetime.now().day))
        self.record_date_line.setFixedWidth(120)
        self.source_account_box = QComboBox()
        self.record_type_box = QComboBox()
        self.record_type_box.addItems(log_types)
        self.record_type_box.currentIndexChanged.connect(self.record_type_changed)
        self.destination_account_box = QComboBox()
        self.destination_account_box.setVisible(False)
        self.rebox()
        self.amount_line = QLineEdit()
        self.amount_line.setValidator(QRegExpValidator(QRegExp(r'[0-9]+\.?[0-9]+')))
        self.amount_line.setFixedWidth(100)
        self.desc_line = QLineEdit()
        self.confirmbtn = QPushButton('确认')
        self.confirmbtn.setFixedWidth(40)
        self.confirmbtn.clicked.connect(self.log_append)
        self.dellogbtn = QPushButton('删除')
        self.dellogbtn.setFixedWidth(40)
        self.dellogbtn.clicked.connect(self.log_removal)
        bottonlayout.addWidget(QLabel('日期'))
        bottonlayout.addWidget(self.record_date_line)
        bottonlayout.addWidget(self.source_account_box)
        bottonlayout.addWidget(self.record_type_box)
        bottonlayout.addWidget(QLabel('金额'))
        bottonlayout.addWidget(self.amount_line)
        bottonlayout.addWidget(QLabel('附言'))
        bottonlayout.addWidget(self.desc_line)
        bottonlayout.addWidget(self.destination_account_box)
        bottonlayout.addWidget(self.confirmbtn)
        bottonlayout.addWidget(self.dellogbtn)

        mainLayout.addLayout(downlayout)
        mainLayout.addLayout(bottonlayout)

        self.investsLayout = QHBoxLayout()
        self.investsLayout.addStretch(40)
        self.investsLayout.addWidget(QLabel('投资类型'))
        self.invests_types_combobox = QComboBox()
        self.invests_types_combobox.addItems(('比特币', '基金', '股票'))
        self.investsLayout.addWidget(self.invests_types_combobox)
        self.investsLayout.addWidget(QLabel('代码'))
        self.invests_codes_line = QLineEdit()
        self.invests_codes_line.setValidator(QRegExpValidator(QRegExp(r'[0-9]+$')))
        self.investsLayout.addWidget(self.invests_codes_line)
        self.investsLayout.addWidget(QLabel('份额'))
        self.invests_quantity_line = QLineEdit()
        self.invests_quantity_line.setValidator(QRegExpValidator(QRegExp(r'[0-9]+\.?[0-9]+')))
        self.investsLayout.addWidget(self.invests_quantity_line)
        self.investsLayout.addWidget(QLabel('单价'))
        self.invests_price_line = QLineEdit()
        self.invests_price_line.setValidator(QRegExpValidator(QRegExp(r'[0-9]+\.?[0-9]+')))
        self.investsLayout.addWidget(self.invests_price_line)
        mainLayout.addLayout(self.investsLayout)

        self.setLayout(mainLayout)
        self.refresh_all()

    def init_tree(self):
        self.myAccountsItems.clear()
        self.leftTree.clear()
        topAcc = QTreeWidgetItem()
        topAcc.setText(0, TOPLEVEL)
        self.leftTree.addTopLevelItem(topAcc)
        self.myAccountsItems[TOPLEVEL] = topAcc

    def price_received(self, data):
        self.prices = data
        self.calculate_invests()

    def calculate_invests(self):
        if not self.prices:
            return
        data = self.prices
        index = self.invests[self.invests['类型'] == '比特币']['当前价格'].index
        self.invests.iloc[index, 6] = data['btc']
        if data['fund']:
            funds = self.invests[self.invests['类型'] == '基金']['代码']
            for index in funds.index:
                self.invests.iloc[index, 2] = data['fund'][self.invests.iloc[index, 1]][0]
                try:
                    self.invests.iloc[index, 6] = float(data['fund'][self.invests.iloc[index, 1]][1])
                except ValueError:
                    self.invests.iloc[index, 6] = 0
        if data['stock']:
            # TODO
            # for each in data['stock']:
            #     index = self.invests[(self.invests['类型'] == '股票') & (self.invests['代码'] == each)]['当前价格']
            #     self.invests.iloc[index, 6] = data['stock'][each]
            pass
        self.invests['当前市值'] = self.invests['当前价格'] * self.invests['持有份额']
        self.invests['累计盈亏'] = self.invests['当前市值'] - self.invests['投入资本']
        self.invests['收益率'] = (self.invests['当前市值'] - self.invests['投入资本']) / self.invests['投入资本']
        self.refresh_all()
        self.save_data()

    def save_data(self):
        self.logs.to_csv(PATH + LogFile, index=False)
        self.invests.to_csv(PATH + InvestsFile, index=False)

    def refresh_all(self):
        self.myAccountsItems[TOPLEVEL].setText(1, '{:.2f}'.format(self.logs['金额'].sum() + self.invests['当前市值'].sum()))
        for each in self.logs.groupby('账户类型'):
            if each[0] in self.myAccountsItems.keys():
                self.myAccountsItems[each[0]].setText(1, '{:.2f}'.format(each[1]['金额'].sum()))
            else:
                treeitem = QTreeWidgetItem()
                treeitem.setText(0, each[0])
                treeitem.setText(1, '{:.2f}'.format(each[1]['金额'].sum()))
                self.myAccountsItems[TOPLEVEL].addChild(treeitem)
                self.myAccountsItems[each[0]] = treeitem
        for each in self.logs.groupby('发起账户'):
            if each[0] in self.myAccountsItems.keys():
                self.myAccountsItems[each[0]].setText(1, '{:.2f}'.format(each[1]['金额'].sum()))
            else:
                titem = QTreeWidgetItem()
                titem.setText(0, each[0])
                titem.setText(1, '{:.2f}'.format(self.logs[self.logs['发起账户'] == each[0]]['金额'].sum()))
                titem.setTextAlignment(1, Qt.AlignCenter)
                self.myAccountsItems[each[1].iloc[0, -1]].addChild(titem)
                self.myAccountsItems[each[0]] = titem
        if '我的投资' in self.myAccountsItems.keys():
            self.myAccountsItems['我的投资'].setText(1, '{:.2f}'.format(self.invests['当前市值'].sum()))
        else:
            treeitem = QTreeWidgetItem()
            treeitem.setText(0, '我的投资')
            treeitem.setText(1, '{:.2f}'.format(self.invests['当前市值'].sum()))
            self.myAccountsItems[TOPLEVEL].addChild(treeitem)
            self.myAccountsItems['我的投资'] = treeitem
        for each in self.invests.groupby('类型'):
            if each[0] in self.myAccountsItems.keys():
                self.myAccountsItems[each[0]].setText(1, '{:.2f}'.format(each[1]['当前市值'].sum()))
            else:
                treeitem = QTreeWidgetItem()
                treeitem.setText(0, each[0])
                treeitem.setText(1, '{:.2f}'.format(each[1]['当前市值'].sum()))
                self.myAccountsItems['我的投资'].addChild(treeitem)
                self.myAccountsItems[each[0]] = treeitem
        self.leftTree.expandAll()
        self.leftTree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        current_table_text = self.leftTree.currentItem().text(0) if self.leftTree.currentItem() else TOPLEVEL
        self.display_table(current_table_text)

    def display_table(self, _name):
        self.rightTable.clear()

        def place_item(itemlist):
            self.rightTable.setRowCount(len(itemlist))
            for r_idx, row in enumerate(itemlist.index):
                for c_idx, data in enumerate(itemlist.loc[row]):
                    if str(data) in ('None', 'nan'):
                        continue
                    elif isinstance(data, pd.datetime):
                        titem = QTableWidgetItem(data.strftime('%Y-%m-%d'))
                        titem.setTextAlignment(Qt.AlignCenter)
                        titem.setData(1000, data.timestamp())
                    else:
                        if isinstance(data, (float, int)):
                            text = '{:.2f}'.format(data) if abs(data) > 100 else '{:.4f}'.format(data)
                        else:
                            text = str(data)
                        titem = QTableWidgetItem(text)
                        titem.setData(1000, data)
                        titem.setTextAlignment(Qt.AlignCenter)
                    self.rightTable.setItem(r_idx, c_idx, titem)
        if _name in ('我的投资', '比特币', '基金', '股票'):
            self.rightTable.setColumnCount(len(self.invests.columns))
            self.rightTable.setHorizontalHeaderLabels(list(self.invests.columns))
            if _name != '我的投资':
                place_item(self.invests[self.invests['类型'] == _name])
            else:
                place_item(self.invests)
        else:
            self.rightTable.setColumnCount(len(self.logs.columns[:-1]))
            self.rightTable.setHorizontalHeaderLabels(list(self.logs.columns)[:-1])
            if _name == TOPLEVEL:
                place_item(self.logs)
            elif _name in SUBLEVEL:
                place_item(self.logs[self.logs['账户类型'] == _name])
            else:
                place_item(self.logs[self.logs['发起账户'] == _name])

    def tree_item_clicked(self, item):
        _name = item.text(0)
        self.display_table(_name)
        if _name in ('我的投资', '比特币', '基金', '股票'):
            self.displayBar.setText(self.invests_display(_name))
        else:
            self.displayBar.setText(self.account_display(_name))
        self.balnameline.setText(_name)

    def invests_display(self, acc_name):
        ret = '[{}]\t 成本 {:.2f} 元\t市值 {:.2f} 元\t收益 {:.2f}\t收益率 {:.2%}'
        if acc_name == '我的投资':
            this = self.invests
        else:
            this = self.invests[self.invests['类型'] == acc_name]
        invested = this['投入资本'].sum()
        worthy = this['当前市值'].sum()
        return ret.format(acc_name, invested, worthy, worthy - invested, (worthy - invested) / invested)

    def account_display(self, acc_name):
        ret = '[{}]\t 净流入 {} 元\t净流出 {} 元'
        if TOPLEVEL in acc_name:
            acc = self.logs
        else:
            types = '发起账户' if acc_name not in ('我有的', '要还的', '欠我的') else '账户类型'
            acc = self.logs[(self.logs[types] == acc_name)]
        income = acc[(acc['金额'] > 0)]['金额'].sum()
        outcome = acc[(acc['金额'] < 0)]['金额'].sum()
        return ret.format(acc_name, income, outcome)

    def add_accounts(self):
        bname = self.balnameline.text()
        if not bname:
            return
        self.logs = self.logs.append(
            pd.Series([pd.datetime.now(), bname, '新建', 0, np.nan, np.nan, self.baltypebox.currentText()],
                      index=self.logs.columns,
                      name=self.logs.index[-1] + 1))
        self.rebox()
        self.refresh_all()

    def del_accounts(self):
        bname = self.balnameline.text()
        if not bname or bname in [TOPLEVEL] + SUBLEVEL:
            return
        confirm = QMessageBox().warning(self, '确认删除', '正在删除[{}]所有记录'.format(bname),
                                        QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.No:
            return
        self.logs = self.logs[self.logs['发起账户'] != bname]
        self.rebox()
        self.init_tree()
        self.refresh_all()

    def record_type_changed(self, index):
        if index in (3, 4, 5, 6):
            self.destination_account_box.setVisible(True)
        else:
            self.destination_account_box.setVisible(False)

    def log_append(self):
        r_type = self.record_type_box.currentText()
        if r_type in ('投资', '赎回'):
            self.invests_append(r_type)
            return
        date = self.record_date_line.date()
        hour, minute, sec = pd.datetime.now().hour, pd.datetime.now().minute, pd.datetime.now().second
        date = pd.datetime(date.year(), date.month(), date.day(), hour, minute, sec)
        source_acc = self.source_account_box.currentText()
        amount = float(self.amount_line.text())
        if r_type in ['支出', '转出', '贷款', '还款', '借出']:
            amount = -amount
        if r_type == '调整':
            amount = amount - self.logs[self.logs['发起账户'] == source_acc]['金额'].sum()
        dest_acc = self.destination_account_box.currentText() if self.destination_account_box.isVisible() else np.nan
        notes = self.desc_line.text()
        acc_type = self.logs[self.logs['发起账户'] == source_acc]['账户类型'].values[0]
        self.logs = self.logs.append(pd.Series([date, source_acc, r_type, amount, dest_acc, notes, acc_type],
                                               index=self.logs.columns), ignore_index=True)
        if self.destination_account_box.isVisible():
            acc_type = self.logs[self.logs['发起账户'] == dest_acc]['账户类型'].values[0]
            self.logs = self.logs.append(pd.Series([date, dest_acc, oppo_log_types[r_type], -amount, source_acc,
                                                    notes, acc_type], index=self.logs.columns), ignore_index=True)
        self.re_index_logs()
        self.refresh_all()

    def invests_append(self, r_type):
        itypes = self.invests_types_combobox.currentText()
        code = self.invests_codes_line.text()
        if itypes in ('基金', '股票') and not code:
            return
        source_acc = self.source_account_box.currentText()
        if self.amount_line.text() and self.invests_price_line.text():
            amount = float(self.amount_line.text())
            unit_price = float(self.invests_price_line.text())
            quantity = amount / unit_price
        elif self.invests_price_line.text() and self.invests_quantity_line.text():
            quantity = float(self.invests_quantity_line.text())
            unit_price = float(self.invests_price_line.text())
            amount = quantity * unit_price
        elif self.amount_line.text() and self.invests_quantity_line.text():
            amount = float(self.amount_line.text())
            quantity = float(self.invests_quantity_line.text())
            unit_price = amount / quantity
        else:
            return

        if r_type == '赎回':
            amount = -amount
            quantity = -quantity

        acc_type = self.logs[self.logs['发起账户'] == source_acc]['账户类型'].values[0]
        self.logs = self.logs.append(pd.Series({'日期': pd.datetime.now(),
                                                '发起账户': source_acc,
                                                '类型': r_type,
                                                '金额': -amount,
                                                '目标账户': np.nan,
                                                '附言': '{}|{}|{}'.format(itypes, code, quantity),
                                                '账户类型': acc_type}), ignore_index=True)
        rst = self.invests[(self.invests['类型'] == itypes) & (self.invests['代码'] == code)]
        if len(rst):
            remain = rst['持有份额'].iloc[0] + quantity
            if remain < 0:
                remain = 0
                amount = unit_price * rst['持有份额']
            rst['持有份额'].iloc[0] = remain
            rst['投入资本'].iloc[0] += amount
            rst['持仓成本'] = rst['投入资本'] / rst['持有份额']
            self.invests.update(rst)
        else:
            self.invests = self.invests.append(
                pd.Series([itypes, code, None, quantity, unit_price, amount, 0, None, None],
                          index=self.invests.columns), ignore_index=True)
        self.re_index_logs()
        self.calculate_invests()
        self.refresh_all()
        self.save_data()

    def log_removal(self):
        types = self.leftTree.currentItem().text(0)
        # those selections within the categories below are not allowed to delete,
        # it only can be reduced by deleting from others until quantity become to 0, then it will be deleted.
        if types in ('我的投资', '比特币', '基金', '股票'):
            return
        _row = self.rightTable.currentRow()
        if _row != -1:
            ts = self.rightTable.item(_row, 0).data(1000)
            amount = self.rightTable.item(_row, 3).data(1000)
            # catch the pieces that need to be deleted.
            linesToDel = self.logs[((self.logs['金额'] == amount) | (self.logs['金额'] == -amount))
                                   & (self.logs['日期'] == pd.datetime.fromtimestamp(ts))]
            self.logs.drop(linesToDel.index, inplace=True)
            if linesToDel['类型'].iloc[0] in ('投资', '赎回'):
                sub_type, code, quantity = linesToDel['附言'].iloc[0].split('|')
                rst = self.invests[(self.invests['类型'] == sub_type) & (self.invests['代码'] == code)]
                rst['持有份额'] -= float(quantity)
                rst['投入资本'] += amount
                rst['持仓成本'] = rst['投入资本'] / rst['持有份额']
                self.invests.update(rst)
            self.re_index_logs()
            self.calculate_invests()
            self.refresh_all()
            self.save_data()

    def re_index_logs(self):
        self.logs = self.logs.sort_values('日期')
        self.logs.index = range(len(self.logs))

    def rebox(self):
        self.source_account_box.clear()
        self.destination_account_box.clear()
        self.source_account_box.addItems([x[0] for x in self.logs.groupby('发起账户')])
        self.destination_account_box.addItems([x[0] for x in self.logs.groupby('发起账户')])


app = QApplication([])

win = MainWin()
win.show()

app.exec()
