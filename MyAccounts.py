from smb.SMBConnection import SMBConnection
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import os
import pickle
import re
import tempfile


class Balance(list):
    def __init__(self, bal_name, bal_type):
        super().__init__()
        self.name = bal_name
        self.bal_type = bal_type
        self.balance = 0

    def record(self, date, _type, _amount, _other=None, _descrip=None, ):
        self.balance += _amount
        self.append((self.name, date, _type, _amount, _other, _descrip))


class Account(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.acc_name = '我的账户'

    def set_name(self, acc_name):
        self.acc_name = acc_name

    def add_balcance(self, bal_name, bal_type):
        self[bal_name] = Balance(bal_name, bal_type)

    def operate(self, date, bal_name, _type, _amount, _other_name=None, _descrip=None):
        if bal_name in self.keys():
            self[bal_name].record(date, _type, _amount, _other_name, _descrip)
            if _other_name:
                self[_other_name].record(date, _type, -_amount, bal_name, _descrip)
        else:
            return False

    def remove_record(self, log):
        log[3] = float(log[3])
        if log[0] in self.keys():
            self[log[0]].balance -= log[3]
            self[log[0]].remove(tuple(log))
        if log[4]:
            log[0], log[4] = log[4], log[0]
            log[3] = -log[3]
            self[log[0]].balance -= log[3]
            self[log[0]].remove(tuple(log))


class MainWin(QWidget):
    btype = {'我有的': 0, '要还的': 1, '欠我的': 2}

    def __init__(self, parent=None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.setWindowTitle('记账薄')
        self.setMinimumWidth(1280)
        self.accounts = Account()
        self.accounts_category = {}
        self.load_data()
        mainlayout = QVBoxLayout()
        toplayout = QHBoxLayout()
        savebtn = QPushButton('保存')
        savebtn.setFixedWidth(50)
        savebtn.clicked.connect(self.save_data)
        toplayout.addWidget(savebtn)
        self.displaybar = QLabel()
        toplayout.addWidget(self.displaybar, alignment=Qt.AlignCenter)
        mainlayout.addLayout(toplayout)

        downlayout = QHBoxLayout()
        self.leftsidetree = QTreeWidget()
        self.leftsidetree.setColumnCount(2)
        self.leftsidetree.setHeaderHidden(True)
        self.leftsidetree.setMaximumWidth(300)
        self.leftsidetree.itemClicked.connect(self.treeitemclicked)
        self.rightsidetable = QTableWidget()
        self.rightsidetable.setMinimumWidth(500)
        self.rightsidetable.setSelectionBehavior(QTableWidget.SelectRows)
        self.rightsidetable.setSelectionMode(QTableWidget.SingleSelection)
        self.rightsidetable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        downlayout.addWidget(self.leftsidetree, alignment=Qt.AlignJustify)
        downlayout.addWidget(self.rightsidetable)

        bottonlayout = QHBoxLayout()
        self.balnameline = QLineEdit()
        self.balnameline.setFixedWidth(80)
        self.baltypebox = QComboBox()
        self.baltypebox.setFixedWidth(65)
        self.baltypebox.addItems(('我有的', '要还的', '欠我的'))
        self.addbalbtn = QPushButton('添加')
        self.addbalbtn.setFixedWidth(40)
        self.addbalbtn.clicked.connect(self.addbalacc)
        self.delbalbtn = QPushButton('删除')
        self.delbalbtn.setFixedWidth(40)
        self.delbalbtn.clicked.connect(self.delbalacc)

        bottonlayout.addWidget(self.balnameline)
        bottonlayout.addWidget(self.baltypebox)
        bottonlayout.addWidget(self.addbalbtn)
        bottonlayout.addWidget(self.delbalbtn)
        bottonlayout.addStretch(1)

        self.record_date_line = QLineEdit()
        self.record_date_line.setFixedWidth(70)
        self.source_account_box = QComboBox()
        self.source_account_box.addItems(sorted(self.accounts.keys()))
        self.record_type_box = QComboBox()
        self.record_type_box.addItems(('支出', '收入', '转账', '借出', '收回', '借入', '返还'))
        self.record_type_box.currentIndexChanged.connect(self.record_type_changed)
        self.destination_account_box = QComboBox()
        self.destination_account_box.setVisible(False)
        self.destination_account_box.addItems(sorted(self.accounts.keys()))
        self.amount_line = QLineEdit()
        self.amount_line.setFixedWidth(100)
        self.desc_line = QLineEdit()
        self.confirmbtn = QPushButton('确认')
        self.confirmbtn.setFixedWidth(40)
        self.confirmbtn.clicked.connect(self.record_confirmed)
        self.dellogbtn = QPushButton('删除')
        self.dellogbtn.setFixedWidth(40)
        self.dellogbtn.clicked.connect(self.dellog_confirmed)
        bottonlayout.addWidget(QLabel('日期'))
        bottonlayout.addWidget(self.record_date_line)
        bottonlayout.addWidget(self.source_account_box)
        bottonlayout.addWidget(self.record_type_box)
        bottonlayout.addWidget(QLabel('金额'))
        bottonlayout.addWidget(self.amount_line)
        bottonlayout.addWidget(QLabel('描述'))
        bottonlayout.addWidget(self.desc_line)
        bottonlayout.addWidget(self.destination_account_box)
        bottonlayout.addWidget(self.confirmbtn)
        bottonlayout.addWidget(self.dellogbtn)

        mainlayout.addLayout(downlayout)
        mainlayout.addLayout(bottonlayout)
        self.setLayout(mainlayout)
        self.display_tree()
        self.display_table('我的账户')

    def save_data(self):
        smb_connection = SMBConnection('', '', '', 'ws832', use_ntlm_v2=True)
        smb_connection.connect('192.168.0.1', 445)
        with tempfile.TemporaryFile() as f:
            f.write(pickle.dumps(self.accounts))
            f.seek(0)
            smb_connection.storeFile('WS832', 'Norelsys-2537BCDE_usb1_1/MyAccounts/MyAccounts.dat', f)

    def load_data(self):
        smb_connection = SMBConnection('', '', '', 'ws832', use_ntlm_v2=True)
        smb_connection.connect('192.168.0.1', 445)
        with tempfile.TemporaryFile() as f:
            smb_connection.retrieveFile('WS832', 'Norelsys-2537BCDE_usb1_1/MyAccounts/MyAccounts.dat', f)
            f.seek(0)
            self.accounts = pickle.loads(f.read())

    def display_tree(self):
        self.leftsidetree.clear()
        accoutitem = QTreeWidgetItem()
        accoutitem.setText(0, self.accounts.acc_name)
        self.leftsidetree.addTopLevelItem(accoutitem)
        for i, each in enumerate(('我有的', '要还的', '欠我的')):
            treeitem = QTreeWidgetItem()
            treeitem.setText(0, each)
            accoutitem.addChild(treeitem)
            self.accounts_category[i] = treeitem
        for each in self.accounts:
            titem = QTreeWidgetItem()
            titem.setText(0, each)
            titem.setText(1, str(self.accounts[each].balance))
            titem.setTextAlignment(1, Qt.AlignCenter)
            self.accounts_category[self.accounts[each].bal_type].addChild(titem)
        self.leftsidetree.expandAll()
        self.leftsidetree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        treeitem = self.leftsidetree.currentItem()
        if treeitem:
            self.display_table(treeitem.text(0))
        else:
            self.display_table(self.accounts.acc_name)

    def addbalacc(self):
        bname = self.balnameline.text()
        if not bname:
            return
        self.accounts.add_balcance(bname, self.btype[self.baltypebox.currentText()])
        self.save_data()
        self.display_tree()
        self.source_account_box.clear()
        self.source_account_box.addItems(sorted(self.accounts.keys()))
        self.destination_account_box.clear()
        self.destination_account_box.addItems(sorted(self.accounts.keys()))

    def delbalacc(self):
        item = self.leftsidetree.currentItem()
        if item.text(0) in ('我的账户', '我有的', '要还的', '欠我的'):
            return
        confirm = QMessageBox().warning(self, '确认删除', '确定要删除账户[{}]吗?'.format(item.text(0)),
                                        QMessageBox.Yes|QMessageBox.No)
        if confirm == QMessageBox.No:
            return
        del self.accounts[item.text(0)]
        self.save_data()
        self.display_tree()
        self.source_account_box.clear()
        self.source_account_box.addItems(sorted(self.accounts.keys()))
        self.destination_account_box.clear()
        self.destination_account_box.addItems(sorted(self.accounts.keys()))

    def treeitemclicked(self, item):
        _name = item.text(0)
        self.display_table(_name)
        if _name not in self.accounts:
            return
        self.balnameline.setText(_name)

    def display_table(self, _name=None):
        if not _name:
            _name = self.accounts.acc_name
        total = 0
        current = 0
        debt = 0
        getback = 0
        for each in self.accounts:
            total += self.accounts[each].balance
            if self.accounts[each].bal_type == 0:
                current += self.accounts[each].balance
            elif self.accounts[each].bal_type == 1:
                debt += self.accounts[each].balance
            elif self.accounts[each].bal_type == 2:
                getback += self.accounts[each].balance

        self.displaybar.setText('总资产: {}    现有资产: {}    负债: {}    待收: {}'
                                .format(total, current, debt, getback))
        self.rightsidetable.clear()
        self.rightsidetable.setColumnCount(6)
        self.rightsidetable.setHorizontalHeaderLabels(('发生账户', '日期', '类型', '金额', '关联账户', '描述'))
        def place_item(itemlist):
            _items = sorted(itemlist, key=lambda x:x[1])
            self.rightsidetable.setRowCount(len(_items))
            for i, each in enumerate(_items):
                for n in range(len(each)):
                    if each[n]:
                        titem = QTableWidgetItem(str(each[n]))
                        titem.setTextAlignment(Qt.AlignCenter)
                        self.rightsidetable.setItem(i, n, titem)

        if _name == '我的账户':
            _takeall = []
            for each in self.accounts:
                _takeall.extend(self.accounts[each])
            place_item(_takeall)
        elif _name in ('我有的', '要还的', '欠我的'):
            _takesome = []
            for each in self.accounts:
                if self.accounts[each].bal_type == self.btype[_name]:
                    _takesome.extend(self.accounts[each])
            place_item(_takesome)
        else:
            _takesingle = sorted(self.accounts[_name])
            place_item(_takesingle)

    def record_type_changed(self, index):
        if index > 1:
            self.destination_account_box.setVisible(True)
        else:
            self.destination_account_box.setVisible(False)

    def record_confirmed(self):
        date = self.check_date(self.record_date_line.text())
        if not date:
            return
        amount = self.amount_line.text()
        try:
            amount = float(amount)
        except ValueError:
            return
        s_name = self.source_account_box.currentText()
        if self.record_type_box.currentIndex() <= 1:
            self.accounts.operate('-'.join(date), s_name, self.record_type_box.currentText(), amount,
                                          _descrip=self.desc_line.text())
        if self.record_type_box.currentIndex() > 1:
            d_name = self.destination_account_box.currentText()
            self.accounts.operate('-'.join(date), s_name, self.record_type_box.currentText(), amount, d_name,
                                          _descrip=self.desc_line.text())
        self.display_tree()
        self.display_table(self.accounts.acc_name)

    def dellog_confirmed(self):
        _row = self.rightsidetable.currentRow()
        _remove_item = []
        for each in range(6):
            try:
                _remove_item.append(self.rightsidetable.item(_row, each).text())
            except AttributeError:
                _remove_item.append(None)
        self.accounts.remove_record(_remove_item)
        self.display_tree()

    @staticmethod
    def check_date(date):
        try:
            return re.search(r'(\d{4})-?(\d{2})-?(\d{2})$', date).groups()
        except AttributeError:
            return False


app = QApplication([])

win = MainWin()
win.show()

app.exec()
