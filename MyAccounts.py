import pandas as pd
import numpy as np
from PyQt5.QtWidgets import QWidget, QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QVBoxLayout, \
    QHBoxLayout, QPushButton, QLabel, QLineEdit, QComboBox, QMessageBox, QApplication, QHeaderView
from PyQt5.QtCore import QThread, pyqtSignal, Qt
import re
import sys
import os
import requests
import json
import time

PATH = sys.argv[0][:sys.argv[0].rfind(os.sep)+1] if os.sep in sys.argv[0] else ''
FileName = 'my_logs.csv'
if FileName not in os.listdir():
    pd.DataFrame([], columns='日期,发起账户,类型,金额,目标账户,附言,账户类型'.split(',')).to_csv(PATH + FileName, index=False)
TOPLEVEL = '所有账户'
SUBLEVEL = ['我有的', '要还的', '欠我的']
log_types = ['收入', '支出', '调整', '转出', '贷款', '还款', '借出']
oppo_log_types = {'转出': '转入', '贷款': '借入', '还款': '消贷', '借出': '待收'}
BitCoinAccountName = '比特币'


class Bitcoin(QThread):
    price_sender = pyqtSignal(float)
    price = 0

    def run(self):
        while True:
            try:
                sells = json.loads(requests.get('https://localbitcoins.com/sell-bitcoins-online/cny/.json').text)
                price = float(sells['data']['ad_list'][0]['data']['temp_price'])
                if self.price != price:
                    self.price_sender.emit(price)
                    self.price = price
            except Exception:
                pass
            time.sleep(60)


class MainWin(QWidget):
    def __init__(self, parent=None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.setWindowTitle('羊家记账薄')
        self.setMinimumWidth(1280)
        self.myAccountsItems = {}
        self.bitcoin = Bitcoin()
        self.bitcoin.price_sender.connect(self.refresh_all)
        self.bitcoin.start()
        self.logs = self.load_data()

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

        self.record_date_line = QLineEdit()
        self.record_date_line.setFixedWidth(70)
        self.source_account_box = QComboBox()
        self.record_type_box = QComboBox()
        self.record_type_box.addItems(log_types)
        self.record_type_box.currentIndexChanged.connect(self.record_type_changed)
        self.destination_account_box = QComboBox()
        self.destination_account_box.setVisible(False)
        self.rebox()
        self.amount_line = QLineEdit()
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
        self.setLayout(mainLayout)
        self.refresh_all()
        self.btc_timer = self.startTimer(1000 * 30)

    def init_tree(self):
        self.myAccountsItems.clear()
        self.leftTree.clear()
        topAcc = QTreeWidgetItem()
        topAcc.setText(0, TOPLEVEL)
        self.leftTree.addTopLevelItem(topAcc)
        self.myAccountsItems[TOPLEVEL] = topAcc

    def timerEvent(self, QTimerEvent):
        if QTimerEvent.timerId() == self.btc_timer:
            self.refresh_all()

    def save_data(self):
        self.logs.to_csv(PATH + FileName, index=False)

    @staticmethod
    def load_data():
        ret = pd.read_csv(PATH + FileName, converters={'日期': pd.to_datetime})
        return ret.sort_values('日期')

    def bitcoin_handler(self, price):
        bitcoinRows = self.logs[self.logs['发起账户'] == BitCoinAccountName]
        bitcoins = pd.to_numeric(bitcoinRows['附言']).sum()
        total = bitcoins * price
        invests = bitcoinRows[bitcoinRows['类型'] != '盈利']['金额'].sum()
        rewards = total - invests if total else 0
        self.logs = self.logs.drop(self.logs[(self.logs['发起账户'] == BitCoinAccountName) & (self.logs['类型'] == '盈利')].index)
        self.logs = self.logs.append(pd.Series({'日期': pd.datetime.now(),
                                                '发起账户': BitCoinAccountName,
                                                '类型': '盈利',
                                                '金额': round(rewards, 2),
                                                '目标账户': np.nan,
                                                '附言': np.nan,
                                                '账户类型': SUBLEVEL[0]}), ignore_index=True)

    def refresh_all(self, bitcoin_price=0):
        if bitcoin_price:
            self.bitcoin_handler(bitcoin_price)

        self.myAccountsItems[TOPLEVEL].setText(1, '{:.2f}'.format(self.logs['金额'].sum()))
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
        self.leftTree.expandAll()
        self.leftTree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        current_table_text = self.leftTree.currentItem().text(0) if self.leftTree.currentItem() else TOPLEVEL
        self.display_table(current_table_text)

    def display_table(self, _name):
        self.rightTable.clear()
        self.rightTable.setColumnCount(len(self.logs.columns[:-1]))
        self.rightTable.setHorizontalHeaderLabels(list(self.logs.columns)[:-1])

        def place_item(itemlist):
            self.rightTable.setRowCount(len(itemlist))
            for r_idx, row in enumerate(itemlist.index):
                for c_idx, text in enumerate(itemlist.loc[row]):
                    if str(text) in ('None', 'nan'):
                        continue
                    elif isinstance(text, pd.datetime):
                        titem = QTableWidgetItem(text.strftime('%Y-%m-%d'))
                        titem.setTextAlignment(Qt.AlignCenter)
                        titem.setData(1000, text.timestamp())
                    else:
                        titem = QTableWidgetItem(str(text))
                        titem.setTextAlignment(Qt.AlignCenter)
                    self.rightTable.setItem(r_idx, c_idx, titem)

        if _name == TOPLEVEL:
            place_item(self.logs)
        elif _name in ('我有的', '要还的', '欠我的'):
            place_item(self.logs[self.logs['账户类型'] == _name])
        else:
            place_item(self.logs[self.logs['发起账户'] == _name])

    def tree_item_clicked(self, item):
        _name = item.text(0)
        self.display_table(_name)
        if _name == '比特币':
            self.displayBar.setText(self.bitcoin_display())
        else:
            self.displayBar.setText(self.account_display(_name))

    def bitcoin_display(self):
        ret = '[{}]\t 持有: {} 个\t总成本: {} 元\t单价: {:.2f} 元\t盈亏: {:.2f} 元\t市值: {:.2f} \t收购价: {:.2f} 元'
        bit_acc = self.logs[self.logs['发起账户'] == '比特币']
        total_coins = pd.to_numeric(bit_acc['附言'], errors='coerce').sum()
        total_invested = bit_acc[bit_acc['类型'] == '转入']['金额'].sum()
        profit = bit_acc[bit_acc['类型'] == '盈利']['金额'].sum()
        return ret.format(BitCoinAccountName, total_coins, total_invested, total_invested / total_coins, profit,
                          total_invested + profit, (total_invested + profit) / total_coins)

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
        self.logs = self.logs.append(pd.Series([pd.datetime.now(), bname, '新建', 0, np.nan, np.nan, self.baltypebox.currentText()],
                                               index=self.logs.columns,
                                               name=self.logs.index[-1] + 1))
        self.rebox()
        self.refresh_all()

    def del_accounts(self):
        bname = self.balnameline.text()
        if not bname:
            return
        if bname in [TOPLEVEL] + SUBLEVEL:
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
        if index > 2:
            self.destination_account_box.setVisible(True)
        else:
            self.destination_account_box.setVisible(False)

    def log_append(self):
        try:
            date = self.check_date(self.record_date_line.text())
        except AttributeError:
            QMessageBox().critical(self, '错误信息', '日期格式不正确', QMessageBox.Ok)
            return
        s_name = self.source_account_box.currentText()
        r_type = self.record_type_box.currentText()
        try:
            amount = float(self.amount_line.text())
            if r_type in ['支出', '转出', '贷款', '还款', '借出']:
                amount = -amount
            if r_type == '调整':
                amount = amount - self.logs[self.logs['发起账户'] == s_name]['金额'].sum()
        except ValueError:
            QMessageBox().critical(self, '错误信息', '金额不对', QMessageBox.Ok)
            return
        t_name = self.destination_account_box.currentText() if self.destination_account_box.isVisible() else np.nan
        notes = self.desc_line.text()
        acc_type = self.logs[self.logs['发起账户'] == s_name]['账户类型'].values[0]
        self.logs = self.logs.append(pd.Series([date, s_name, r_type, amount, t_name, notes, acc_type],
                                               index=self.logs.columns, name=len(self.logs)+1))
        if self.destination_account_box.isVisible():
            acc_type = self.logs[self.logs['发起账户'] == t_name]['账户类型'].values[0]
            self.logs = self.logs.append(pd.Series([date, t_name, oppo_log_types[r_type], -amount, s_name, notes, acc_type],
                                                   index=self.logs.columns, name=len(self.logs)+1))
        self.re_index_logs()
        self.refresh_all()

    def re_index_logs(self):
        self.logs = self.logs.sort_values('日期')
        self.logs.index = range(len(self.logs))

    def log_removal(self):
        _row = self.rightTable.currentRow()
        if _row != -1:
            ts = self.rightTable.item(_row, 0).data(1000)
            amount = float(self.rightTable.item(_row, 3).text())
            linesToDel = self.logs[((self.logs['金额'] == amount) | (self.logs['金额'] == -amount))
                                   & (self.logs['日期'] == pd.datetime.fromtimestamp(ts))]
            self.logs.drop(linesToDel.index, inplace=True)
            self.re_index_logs()
            self.refresh_all()

    def rebox(self):
        self.source_account_box.clear()
        self.destination_account_box.clear()
        self.source_account_box.addItems([x[0] for x in self.logs.groupby('发起账户')])
        self.destination_account_box.addItems([x[0] for x in self.logs.groupby('发起账户')])

    @staticmethod
    def check_date(date):
        if not date:
            return pd.datetime.now()
        try:
            return pd.to_datetime(date)
        except pd._libs.tslib.OutOfBoundsDatetime:
            now = pd.datetime.now()
            year = now.year
            try:
                month, day = re.search(r'(\d{2})?-?(\d{2})$', date).groups()
                if not month:
                    month = now.month
                return pd.datetime(year, int(month), int(day))
            except (AttributeError, TypeError):
                raise AttributeError('Bad date type.')

app = QApplication([])

win = MainWin()
win.show()

app.exec()
