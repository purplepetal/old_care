import time

from flask import Flask, render_template, jsonify, request
import pymysql
import datetime
from datetime import date

app = Flask(__name__)

BRANCHNO = ''  # 全局变量保存现在的分店号
NOWSTAFFNO = ''  # 全局变量保存现在的员工号


def conn_db():
    db = pymysql.Connect("localhost", "root", "101010abcABC", "MyMarket")
    return db


# 库存管理货物总库存量
def get_inventory():
    db = conn_db()
    cursor = db.cursor()
    query_inventory = "select bg.gno,gname,outprice,inventory,min_inventory,suno from bg,goods where bg.gno=goods.gno and bno=%s"  # 查询所有看库存
    ret = cursor.execute(query_inventory, BRANCHNO)
    iv_list = []
    if ret > 0:
        content = cursor.fetchall()
        for row in content:
            data = {
                "gno": row[0],
                "gname": row[1],
                "outprice": row[2],
                "inventory": row[3],
                "min_inventory": row[4],
                "suno": row[5]
            }
            print(row[2])
            iv_list.append(data)
    cursor.close()
    db.close()
    return iv_list


# 收支管理模块--获取销售总额、进货总额、进收入
def in_out_pure_money(start_time, end_time, newendstr):
    in_money = 0
    out_money = 0
    in_list = []
    out_list = []
    db = conn_db()
    cursor = db.cursor()
    in_order = "select sono,ssum from sorder where stime>=%s and stime<=%s"  # 查询该时间段内的售货订单
    ret = cursor.execute(in_order, [start_time, newendstr])
    if ret > 0:
        content = cursor.fetchall()
        for row in content:
            data = {
                "orderno": row[0],
                "amt": row[1],
            }
            in_list.append(data)
            in_money = in_money + row[1]
    out_order = "select pono,psum from porder where pindate>=%s and pindate<=%s and pstate=1"  # 查询该时间段内的进货订单
    ret = cursor.execute(out_order, [start_time, end_time])
    if ret > 0:
        content = cursor.fetchall()
        for row in content:
            data = {
                "orderno": row[0],
                "amt": row[1],
            }
            out_list.append(data)
            out_money = out_money + row[1]
    pure_money = in_money - out_money
    dict_money = [{"iv_list": in_list, "profit": pure_money, "total": in_money},
                  {"iv_list": out_list, "profit": pure_money, "total": out_money}]
    cursor.close()
    db.close()
    return dict_money


def modifypurchase(pno, good_list):
    # print(NOWSTAFFNO)
    db = conn_db()
    cursor = db.cursor()
    sql1 = 'select * from pg where pono=%s'
    cursor.execute(sql1, pno)
    contents = cursor.fetchall()
    oldpno = []  # 之前加入过的pno列表
    newpno = []
    for row in contents:
        oldpno.append(row[1])
    for item in good_list:  # {'amount': 22, 'gname': '绿行者沙拉', 'gno': '203040', 'inprice': 4.5}
        getamount = item['amount']
        getno = item['gno']
        newpno.append(getno)  # 最新的gno列表
        flag = getno in oldpno
        if flag:  # 如果之前加入过只需要更新
            sql = 'update pg set pgamt=%s where pono=%s and gno=%s'
            cursor.execute(sql, [getamount, pno, getno])
            db.commit()
        else:  # 之前没加过需要新增一条数据
            sql = 'insert into pg values(%s,%s,%s)'
            cursor.execute(sql, [pno, getno, getamount])
            db.commit()
    for old in oldpno:  # 之前有的后来被删除了
        notexistflag = old not in newpno
        if notexistflag:  # 如果old不在新的gno列表里，证明被删掉了
            sql = 'delete from pg where pono =%s and gno=%s'
            cursor.execute(sql, [pno, old])
            db.commit()
    # 修改porder的sumprice
    sumprice = 0  # 初始化当前的总花费为0
    for gooditem in good_list:
        sumprice = sumprice + gooditem['inprice'] * gooditem['amount']
    sql6 = "update porder set psum=%s where pono=%s"  # 这里是更新porder的sumprice
    cursor.execute(sql6, [sumprice, pno])
    db.commit()
    cursor.close()
    db.close()


@app.route('/getRole', methods=['GET', 'POST'])
def getRole():
    a = request.json
    if a:
        data = a['mydata']
        print(data)
        db = conn_db()
        cursor = db.cursor()
        cursor.execute("select srole from staff where sno=%s", NOWSTAFFNO)
        contents = cursor.fetchall()
        for item in contents:
            role = item[0]
        cursor.close()
        db.close()
        return jsonify(role)

    return jsonify('fail')


# 访问主页，返回主页的html文件
@app.route("/", methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        db = conn_db()
        cursor = db.cursor()
        uno = request.values.get('logno')
        pwd = request.values.get('logpass')
        sql = "select bno from staff where sno=%s and spassword=%s and isexist='y'"
        ret = cursor.execute(sql, [uno, pwd])  # 返回的影响的行数，如果是0，则是查询匹配结果为0行
        if ret > 0:
            global NOWSTAFFNO
            NOWSTAFFNO = uno
            global BRANCHNO
            BRANCHNO = cursor.fetchone()[0]
            cursor.close()
            db.close()
            return render_template('index.html', admin=NOWSTAFFNO)
        else:
            cursor.close()
            db.close()
            return render_template('login.html')

    return render_template('login.html')


####################销售模块

# sell销售功能模块:查询顾客总积分数、检查顾客号是否存在（前端填写会员编号，点击确认按钮时触发）
# 前端发送 1.顾客编号cno            获取方法：cno=request.get_json()['cno']
# 后端：若顾客存在返回总积分数，不存在...
@app.route("/queryCustomer", methods=['POST', 'GET'])
def query_customer():
    if request.method == 'POST':
        cno = request.get_json()['cno']
        db = conn_db()
        cursor = db.cursor()
        sql1 = "select cname from customer where cno=%s"
        ret = cursor.execute(sql1, cno)  # 判断有没有这个顾客
        if ret > 0:  # 有这个顾客
            sql = "select * from customer where cno=%s"  # 获得现有积分
            cursor.execute(sql, cno)
            contents = cursor.fetchall()
            for row in contents:
                point = row[4]
            cursor.close()
            db.close()
            return jsonify(point)
        else:
            cursor.close()
            db.close()
            return jsonify('Failed')


# sell销售功能模块：输入商品编号，点击增加按钮时触发
# 前端发送gno
# 后端返回该商品的相关信息
@app.route("/sell", methods=['POST', 'GET'])
def sell():
    if request.method == 'POST':
        gno = request.get_json()['gno']
        db = conn_db()
        cursor = db.cursor()
        sql1 = "select gname from goods where gno=%s"  # 查询看有没有这个商品
        ret = cursor.execute(sql1, gno)
        if ret > 0:  # 有这个商品
            sql = "select * from goods,bg where goods.gno=bg.gno AND bg.gno=%s AND bg.bno=%s"
            cursor.execute(sql, [gno, BRANCHNO])
            content = cursor.fetchall()
            for row in content:
                print(row)
                getno = row[0]
                getname = row[1]
                getoutprice = row[3]
                getstock = row[9]
            add_good = {
                "gno": getno,
                "gname": getname,
                "outprice": getoutprice,
                "amount": 1,
                "stock": getstock
            }
            cursor.close()
            db.close()
            return jsonify(add_good)
        else:
            cursor.close()
            db.close()
            return jsonify('Failed')
    elif request.method == 'GET':
        return render_template("sell.html")


# sell销售功能模块: 查询顾客可用的积分数（前端点击提交订单按钮时触发）
# 前端发送 1.顾客编号cno，2.顾客购买的商品数组good_list
# 后端返回检查用户是否存在，根据一定规则计算，返回相应的可用积分数
@app.route("/queryPoints", methods=['POST', 'GET'])
def query_point():
    if request.method == 'POST':
        cno = request.get_json()['cno']
        good_list = request.get_json()['good_list']
        db = conn_db()
        cursor = db.cursor()
        sql1 = "select cname from customer where cno=%s"  # 查询看有没有这个顾客
        ret = cursor.execute(sql1, cno)
        if ret > 0:  # 顾客存在
            sql = "select * from customer where cno=%s"  # 获得现有积分
            cursor.execute(sql, cno)
            contents = cursor.fetchall()
            for row in contents:
                point = row[4]  # 顾客现在拥有的积分数
            totalprice = 0  # 初始化当前的总花费为0
            for item in good_list:  # 遍历good_list，多次加和获得最终总花费
                totalprice = totalprice + item['outprice'] * item['amount']
            maxUsingPoint = totalprice * 0.5  # 对于当前订单花费能使用的最大积分数
            if maxUsingPoint > point:
                outputvalue = point
            else:
                outputvalue = maxUsingPoint
            cursor.close()
            db.close()
            return jsonify(round(outputvalue))  # 四舍五入取整传递
        else:
            cursor.close()
            db.close()
            return jsonify('Failed')


# sell销售功能模块：提交售卖订单（前端填写使用积分数，并提交时触发）
# 前端向服务器发送 1.商品数组good_list 2. 使用积分数pointsUsed，后端发送提交成功/失败
@app.route("/submitOrder", methods=['POST', 'GET'])
def submit_order():
    if request.method == 'POST':
        ponitsUsed = request.get_json()['pointsUsed']
        good_list = request.get_json()['good_list']
        cno = request.get_json()['cno']
        # 建立sorder
        db = conn_db()
        cursor = db.cursor(cursor=pymysql.cursors.DictCursor)
        timenowstr = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        orderstr = timenowstr + cno  # 拼接字符串获得订单编号
        sumprice = 0  # 初始化当前的总花费为0
        for item in good_list:  # 遍历good_list，多次加和获得最终总花费
            sumprice = sumprice + (item['outprice'] * item['amount'])
        # 调用存储过程，参数为：顾客号，欲使用积分，订单号，抵现前的总金额，员工号，错误标志位
        cursor.callproc('customer_pay', args=(cno, ponitsUsed, orderstr, sumprice, NOWSTAFFNO, 0))
        # 获取执行完存储的参数
        cursor.execute("select @_customer_pay_5")  # 获得out的参数的值
        result = cursor.fetchall()
        flag = 3  # 负数不合逻辑0，超出原来总积分1，超出限额积分2，对的就是3
        for row in result:
            flag = row['@_customer_pay_5']
        db.commit()
        if flag == 3:
            # 建立sorder之后在sg中插入具体信息
            sql11 = "insert into sg values(%s,%s,%s)"
            for contents in good_list:
                print(contents)
                cursor.execute(sql11, [orderstr, contents['gno'], contents['amount']])
            db.commit()
            return jsonify('提交成功')
        elif flag == 2:
            return jsonify('超出本条订单可以使用的最大积分限额')
        elif flag == 1:
            return jsonify('超出用户当前的总积分数')
        elif flag == 0:
            return jsonify('使用积分数不可以为负数')
        cursor.close()
        db.close()


####################进货模块
# purchase进货功能模块：访问进货页面时触发
# 后端：返回所有进货订单的数组
@app.route('/api/purchase_all')
def index():
    db = conn_db()
    cursor = db.cursor()
    sql = "select * from porder"
    ret = cursor.execute(sql)
    my_list = []
    if ret > 0:  # 进货表里有进货订单
        contents = cursor.fetchall()
        for row in contents:
            # ('20191111101136000001', '000001', 3, '000001', datetime.date(2019, 11, 11), datetime.date(2019, 11, 13), Decimal('87.00'), 1)
            # ('20191201120939000001', '000002', 1, '000001', datetime.date(2019, 12, 1), None, None, 0)
            pono = row[0]  # 遍历获得每一个的订单号
            suno = row[1]
            sno = str(row[2]).zfill(6)  # 如果是000001，就是default相当于没人操作，自动加的订单
            if sno == '000001':
                sno = "---"
            setupdate = row[4].strftime("%Y-%m-%d")
            indate = row[5]
            if indate is None:
                indate = "---"
            else:
                indate = indate.strftime("%Y-%m-%d")
            psum = row[6]
            if psum is None:  # 没写总金额，后端进行计算，更新set
                sumprice = 0  # 初始化当前的总花费为0
                db1 = conn_db()
                cursor1 = db1.cursor()
                sql1 = "select * from pg,goods where pg.gno=goods.gno and pono=%s"  # 找到对应pono的所有商品信息
                ret1 = cursor1.execute(sql1, pono)
                if ret1 > 0:  # 如果有商品信息且SUM为NONE，就计算出来并更新,这里是计算
                    allrows = cursor1.fetchall()
                    # 每一行的内容('2', '111111', 1, '111111', '伊利牛奶', Decimal('25.00'), Decimal('45.00'), 3, 10)
                    for rowitem in allrows:
                        sumprice = sumprice + rowitem[2] * rowitem[5]
                psum = sumprice
                sql2 = "update porder set psum=%s where pono=%s"  # 这里是更新
                cursor1.execute(sql2, [sumprice, pono])
                db1.commit()
                cursor1.close()
                db1.close()
            state = row[7]
            if state == 1:
                statestr = "已完成"
            elif state == 0:
                statestr = "未完成"
            data = {
                "pno": pono,
                "suno": suno,
                "sno": sno,
                "setup_date": setupdate,
                "p_date": indate,
                "pgamt": psum,
                "state": statestr
            }
            my_list.append(data)
        cursor.close()
        db.close()
        return jsonify(my_list)
    else:
        cursor.close()
        db.close()
        return jsonify(my_list)


# purchase进货功能模块：根据订单编号/进货商编号/订单状态/进货商编号+订单状态查询相关订单信息 （点击查询按钮时触发）
# 前端发送pno,suno,state          eg. pno:'D123' , suno:'' , state:'' / pno:'' , suno:'S2213' , state:'未完成'
# 后端返回符合该条件订单的相关信息
@app.route("/purchase", methods=['POST', 'GET'])
def purchase():
    if request.method == 'POST':
        pno = request.get_json()['pno']
        suno = request.get_json()['suno']
        state = request.get_json()['state']
        if pno != '':
            db = conn_db()
            cursor = db.cursor()
            sql1 = "select * from porder where pono=%s"  # 查询看有没有这个进货订单
            ret = cursor.execute(sql1, pno)
            my_list1 = []
            if ret > 0:
                content = cursor.fetchall()
                for row in content:
                    getpono = row[0]
                    getsuno = row[1]
                    getsno = str(row[2]).zfill(6)
                    getsetup = row[4].strftime("%Y-%m-%d")
                    getindate = row[5]
                    if getindate is None:
                        getindate = "---"
                    else:
                        getindate = getindate.strftime("%Y-%m-%d")
                    getamount = row[6]
                    if getamount is None:
                        getamount = 0
                    getstate = row[7]
                    if getstate == 1:
                        statestr = "已完成"
                    elif getstate == 0:
                        statestr = "未完成"
                    data = {
                        "pno": getpono,
                        "suno": getsuno,
                        "sno": getsno,
                        "setup_date": getsetup,
                        "p_date": getindate,
                        "pgamt": getamount,
                        "state": statestr
                    }
                    my_list1.append(data)
            cursor.close()
            db.close()
            return jsonify(my_list1)
        elif suno != '' and state != '':
            db = conn_db()
            cursor = db.cursor()
            sql1 = "select * from porder where suno=%s and pstate=%s"  # 查询看有没有这个进货订单
            ret = cursor.execute(sql1, [suno, int(state)])
            my_list2 = []
            if ret > 0:
                content = cursor.fetchall()
                for row in content:
                    getpono = row[0]
                    getsuno = row[1]
                    getsno = str(row[2]).zfill(6)
                    getsetup = row[4].strftime("%Y-%m-%d")
                    getindate = row[5]
                    if getindate is None:
                        getindate = "---"
                    else:
                        getindate = getindate.strftime("%Y-%m-%d")
                    getamount = row[6]
                    if getamount is None:
                        getamount = 0
                    getstate = row[7]
                    if getstate == 1:
                        statestr = "已完成"
                    elif getstate == 0:
                        statestr = "未完成"
                    data = {
                        "pno": getpono,
                        "suno": getsuno,
                        "sno": getsno,
                        "setup_date": getsetup,
                        "p_date": getindate,
                        "pgamt": getamount,
                        "state": statestr
                    }
                    my_list2.append(data)
            cursor.close()
            db.close()
            return jsonify(my_list2)
        elif suno != '' and state == '':
            db = conn_db()
            cursor = db.cursor()
            sql1 = "select * from porder where suno=%s"  # 查询看有没有这个进货订单
            ret = cursor.execute(sql1, suno)
            my_list3 = []
            if ret > 0:
                content = cursor.fetchall()
                for row in content:
                    getpono = row[0]
                    getsuno = row[1]
                    getsno = str(row[2]).zfill(6)
                    getsetup = row[4].strftime("%Y-%m-%d")
                    getindate = row[5]
                    if getindate is None:
                        getindate = "---"
                    else:
                        getindate = getindate.strftime("%Y-%m-%d")
                    getamount = row[6]
                    if getamount is None:
                        getamount = 0
                    getstate = row[7]
                    if getstate == 1:
                        statestr = "已完成"
                    elif getstate == 0:
                        statestr = "未完成"
                    data = {
                        "pno": getpono,
                        "suno": getsuno,
                        "sno": getsno,
                        "setup_date": getsetup,
                        "p_date": getindate,
                        "pgamt": getamount,
                        "state": statestr
                    }
                    my_list3.append(data)
            cursor.close()
            db.close()
            return jsonify(my_list3)
        elif state != '' and suno == '':
            db = conn_db()
            cursor = db.cursor()
            sql1 = "select * from porder where pstate=%s"  # 查询看有没有这个进货订单
            ret = cursor.execute(sql1, int(state))
            my_list4 = []
            if ret > 0:
                content = cursor.fetchall()
                for row in content:
                    getpono = row[0]
                    getsuno = row[1]
                    getsno = str(row[2]).zfill(6)
                    getsetup = row[4].strftime("%Y-%m-%d")
                    getindate = row[5]
                    if getindate is None:
                        getindate = "---"
                    else:
                        getindate = getindate.strftime("%Y-%m-%d")
                    getamount = row[6]
                    if getamount is None:
                        getamount = 0
                    getstate = row[7]
                    if getstate == 1:
                        statestr = "已完成"
                    elif getstate == 0:
                        statestr = "未完成"
                    data = {
                        "pno": getpono,
                        "suno": getsuno,
                        "sno": getsno,
                        "setup_date": getsetup,
                        "p_date": getindate,
                        "pgamt": getamount,
                        "state": statestr
                    }
                    my_list4.append(data)
            cursor.close()
            db.close()
            return jsonify(my_list4)
        elif pno == '' and state == '' and suno == '':
            return jsonify('Failed')
    elif request.method == 'GET':
        return render_template("purchase.html")


# purchase进货功能模块：未完成的进货订单增加新的商品
# 前端发送供应商编号suno
# 后端：检查供应商是否存在，存在则向porder表中插入新的记录，不存在，则返回'供应商不存在'
@app.route("/add_pOrder", methods=['POST', 'GET'])
def addPorder():
    if request.method == 'POST':
        suno = request.get_json()['suno']
        db = conn_db()
        cursor = db.cursor()
        ret = cursor.execute("select suno from supplier where suno=%s", suno)
        if ret > 0:
            cnt = cursor.execute("select pono from porder where suno=%s and bno=%s and pstate=false", [suno, BRANCHNO])
            if cnt > 0:
                arg = "有向该供货商进货的未完成订单，无需创建"
            else:
                timenowstr = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                orderstr = timenowstr + BRANCHNO + suno  # 拼接字符串获得订单编号
                # pono,suno,sno,bno,setupdate,indate,sum,state
                cursor.execute("insert into porder values(%s,%s,%s,%s,%s,null,null,%s)",
                               [orderstr, suno, 1, BRANCHNO, date.today(), 0])
                db.commit()
                arg = "为您创建一条新的进货订单"
        else:
            arg = "供应商不存在"
        cursor.close()
        db.close()
        return jsonify(arg)


# purchase进货功能模块：未完成的进货订单增加新的商品
# 前端发送要加入的商品编号gno和当前的供货商编号
# 后端：返回该商品的详细信息
@app.route("/add_detail", methods=['POST', 'GET'])
def addDetail():
    if request.method == 'POST':
        gno = request.get_json()['gno']
        suno = request.get_json()['suno']
        db = conn_db()
        cursor = db.cursor()
        sql = "select * from goods where gno=%s"  # 查询这个商品在不在
        amt = cursor.execute(sql, gno)
        if amt > 0:  # 商品存在
            sql1 = "select * from bg where suno=%s and gno=%s"  # 查询看这个供货商有没有这个商品
            ret = cursor.execute(sql1, [suno, gno])
            if ret > 0:  # 当前供货商有这个商品
                sql2 = "select * from goods where gno=%s"
                cursor.execute(sql2, gno)
                content = cursor.fetchall()
                for row in content:
                    getno = row[0]
                    getname = row[1]
                    getinprice = row[2]
                    getmincnt = row[5]
                add_good = {
                    "gno": getno,
                    "gname": getname,
                    "inprice": getinprice,
                    "amount": getmincnt,  # 显示的是默认库存
                }
                cursor.close()
                db.close()
                return jsonify(add_good)
            else:
                cursor.close()
                db.close()
                return jsonify('该供货商不能提供该商品')
        else:
            cursor.close()
            db.close()
            return jsonify('无该商品编号')


# purchase进货模块：未完成的进货订单被修改
# 前端向服务器发送 1.进货订单号 pno 2.修改后的全部商品数组 good_list（该订单中的所有商品）
# 后端根据该数组修改数据库pg的相关信息,并返回相关信息
# 进货订单号: request.get_json()['pno'], 修改后的【全部】商品数组: request.get_json()['good_list']
@app.route("/change_detail", methods=['POST', 'GET'])
def changeDetail():
    if request.method == 'POST':
        pno = request.get_json()['pno']
        good_list = request.get_json()['good_list']
        modifypurchase(pno, good_list)  # 调用修改函数，修改pg
        return jsonify("修改成功")


# purchase进货模块：查询某一进货订单的商品详情
# 前端向服务器发送 1.进货订单号pno
# 后端发送该订单号含有的 1.商品数组
@app.route("/purchase_detail", methods=['POST', 'GET'])
def purchaseDetail():
    if request.method == 'POST':
        pono = request.get_json()['pno']
        db = conn_db()
        cursor = db.cursor()
        sql = "select * from pg,goods where pg.gno=goods.gno and pg.pono=%s"
        ret = cursor.execute(sql, pono)  # 看这个进货订单是否存在
        good_list = []
        if ret > 0:
            contents = cursor.fetchall()
            for row in contents:  # 内容('1', '111111', 2, '111111', '伊利牛奶', Decimal('25.00'), Decimal('45.00'), 3, 10)
                gno = row[1]
                amount = row[2]
                gname = row[4]
                inprice = row[5]
                data = {
                    "gno": gno,
                    "gname": gname,
                    "inprice": inprice,
                    "amount": amount
                }
                good_list.append(data)
            cursor.close()
            db.close()
        return jsonify(good_list)


# purchase进货功能模块：将进货订单修改为进货状态时触发
# 前端发送进货订单号pno 商品数组good_list 进货员编号sno
# 后端：更新商品数组，将状态改为已完成，返回新的进货订单信息
@app.route("/confirmFinish", methods=['POST', 'GET'])
def confirmFinish():
    if request.method == 'POST':
        pno = request.get_json()['pno']
        good_list = request.get_json()['good_list']
        modifypurchase(pno, good_list)  # 调用修改函数，数据库同步更新porder和pg
        db = conn_db()
        cursor = db.cursor()
        sql = 'select * from pg,goods,porder where pg.gno=goods.gno and porder.pono=pg.pono and pg.pono=%s'
        cursor.execute(sql, pno)
        contents = cursor.fetchall()
        # 每个item的格式:
        # ('2', '357897', 5,     [pg]
        # '357897', '奥利奥', Decimal('6.50'), Decimal('15.90'), 10, 50,     [goods]
        # '2', '000001', 2, '000001',datetime.date(2019, 10, 6), None, None, 0)      [porder]
        totalprice = 0
        for item in contents:
            # print(item)
            totalprice = totalprice + item[2] * item[5]  # 获得被修改订单porder的总金额
            # 遍历已经提交的pg的每一条内容，更新库存
            cursor.execute('update bg set inventory=inventory+%s where bno=%s and gno=%s', [item[2], BRANCHNO, item[1]])
        sql1 = 'update porder set psum=%s where pono=%s'
        cursor.execute(sql1, [totalprice, pno])
        sql2 = 'update porder set pstate=%s where pono=%s'
        cursor.execute(sql2, [1, pno])
        sql3 = 'update porder set pindate=%s where pono=%s'
        cursor.execute(sql3, [date.today(), pno])
        sql4 = 'update porder set sno=%s where pono=%s'
        cursor.execute(sql4, [NOWSTAFFNO, pno])
        db.commit()

        pOrder_list = []  # 所有的porder的列表
        sql2 = 'select * from porder'
        cursor.execute(sql2)
        contents2 = cursor.fetchall()
        for row in contents2:
            getpono = row[0]
            getsuno = row[1]
            getsno = str(row[2]).zfill(6)
            getsetup = row[4].strftime("%Y-%m-%d")
            getindate = row[5]
            if getindate is None:
                getindate = "---"
            else:
                getindate = getindate.strftime("%Y-%m-%d")
            getprice = row[6]
            getstate = row[7]
            if getstate == 1:
                statestr = "已完成"
            elif getstate == 0:
                statestr = "未完成"
            data = {
                "pno": getpono,
                "suno": getsuno,
                "sno": getsno,
                "setup_date": getsetup,
                "p_date": getindate,
                "pgamt": getprice,
                "state": statestr
            }
            pOrder_list.append(data)
        cursor.close()
        db.close()
        return jsonify(pOrder_list)


#################### 库存管理模块
@app.route('/api/inventory1')
def inventory1_data():
    iv_list = get_inventory()
    return jsonify(iv_list)


@app.route("/inventory2", methods=['POST', 'GET'])
def inventory2():
    name = request.get_json()['gname']
    db = conn_db()
    cursor = db.cursor()
    query_inventory = "select bg.gno,gname,outprice,inventory,min_inventory,suno from bg,goods where bg.gno=goods.gno and bno=%s and gname like %s"  # 查询所有看库存
    ret = cursor.execute(query_inventory, [BRANCHNO, '%' + name + '%'])
    iv_list = []
    if ret > 0:
        content = cursor.fetchall()
        for row in content:
            data = {
                "gno": row[0],
                "gname": row[1],
                "outprice": row[2],
                "inventory": row[3],
                "min_inventory": row[4],
                "suno": row[5]
            }
            print(row[2])
            iv_list.append(data)
    cursor.close()
    db.close()
    if request.method == 'POST':
        return jsonify(iv_list)
    elif request.method == 'GET':
        return render_template("inventory2.html")


@app.route('/api/inventory2')
def inventory2_data():
    iv_list = get_inventory()
    return jsonify(iv_list)


# 低库存量传值查询界面
@app.route("/inventory3", methods=['POST', 'GET'])
def inventory3():
    amt = request.get_json()['amt']
    db = conn_db()
    cursor = db.cursor()
    query_inventory = "select bg.gno,gname,outprice,inventory,min_inventory,suno from bg,goods where bg.gno=goods.gno and bno=%s and inventory <= %s"  # 查询库存量小于特定值的商品
    ret = cursor.execute(query_inventory, [BRANCHNO, amt])
    iv_list = []
    if ret > 0:
        content = cursor.fetchall()
        for row in content:
            data = {
                "gno": row[0],
                "gname": row[1],
                "outprice": row[2],
                "inventory": row[3],
                "min_inventory": row[4],
                "suno": row[5]
            }
            print(row[2])
            iv_list.append(data)
    cursor.close()
    db.close()
    if request.method == 'POST':
        return jsonify(iv_list)
    elif request.method == 'GET':
        return render_template("inventory3.html")


# 低库存量初始界面
@app.route('/api/inventory3')
def inventory3_data():
    iv_list = get_inventory()
    return jsonify(iv_list)


################### 收支管理模块
@app.route("/money", methods=['POST', 'GET'])
def money():
    if request.method == 'GET':
        return render_template("money.html")


@app.route("/income", methods=['POST', 'GET'])
def income():
    if request.method == 'POST':
        # 获取前端数据
        fyear = request.get_json()['fyear']
        fmonth = request.get_json()['fmonth']
        fday = request.get_json()['fday']
        lyear = request.get_json()['lyear']
        lmonth = request.get_json()['lmonth']
        lday = request.get_json()['lday']
        sart_time = fyear + "-" + fmonth + "-" + fday
        end_time = lyear + "-" + lmonth + "-" + lday
        newendint = int(lday) + 1
        newendday = str(newendint)
        newendstr = lyear + "-" + lmonth + "-" + newendday
        print(sart_time, end_time, newendstr, type(newendstr))
        return in_out_pure_money(sart_time, end_time, newendstr)[0]
    elif request.method == 'GET':
        return render_template("money.html")


@app.route("/outcome", methods=['POST', 'GET'])
def outcome():
    if request.method == 'POST':
        # 获取前端数据
        fyear = request.get_json()['fyear']
        fmonth = request.get_json()['fmonth']
        fday = request.get_json()['fday']
        lyear = request.get_json()['lyear']
        lmonth = request.get_json()['lmonth']
        lday = request.get_json()['lday']
        sart_time = fyear + "-" + fmonth + "-" + fday
        end_time = lyear + "-" + lmonth + "-" + lday
        print(sart_time, end_time)
        newendint = int(lday) + 1
        newendday = str(newendint)
        newendstr = lyear + "-" + lmonth + "-" + newendday
        print(sart_time, end_time, newendstr, type(newendstr))
        return in_out_pure_money(sart_time, end_time, newendstr)[1]
    elif request.method == 'GET':
        return render_template("money.html")


@app.route("/orderinfo", methods=['POST', 'GET'])
def orderinfo():
    db = conn_db()
    cursor = db.cursor()
    iv_list = []
    if request.method == 'POST':
        orderno = request.get_json()['orderno']
        in_out = request.get_json()['in_out']
        print(orderno)
        if in_out == 1:
            sql = "select sg.gno,gname,outprice,sgamt ,goods.outprice*sg.sgamt sum from goods,sg where goods.gno=sg.gno and sono=%s"
        else:
            sql = "select pg.gno,gname,inprice,pgamt ,goods.inprice*pg.pgamt sum from goods,pg where goods.gno=pg.gno and pono=%s"
        cursor.execute(sql, orderno)
        content = cursor.fetchall()
        for row in content:
            data = {
                "gno": row[0],
                "gname": row[1],
                "price": row[2],
                "amt": row[3],
                "sum": row[4],
            }
            iv_list.append(data)
        cursor.close()
        db.close()
        return jsonify(iv_list)
    elif request.method == 'GET':
        return render_template("money.html")


####################人员管理模块

# 初始页面爬取数据
@app.route('/staff_info')
def staff():
    db = conn_db()
    cursor = db.cursor()
    my_list = []
    sql = "select * from staff where isexist='y' and bno=%s"
    ret = cursor.execute(sql, BRANCHNO)
    print(ret)
    if ret > 0:
        contents = cursor.fetchall()
        for row in contents:
            if row[0] == 1:
                print("default")
            else:
                data = {
                    "sno": str(row[0]).zfill(6),
                    "sname": row[1],
                    "bno": row[2],
                    "srole": row[3],
                    "sex": row[4],
                    "sphone": row[5],
                    "joindate": row[6].strftime("%Y-%m-%d"),
                    "spassword": row[7]
                }
                print(type(row[6]))
                my_list.append(data)
    db.close()
    cursor.close()
    return jsonify(my_list)


@app.route('/select_staff', methods=['POST'])
def selectstaff():
    sno = request.get_json()['sno']
    print(sno)
    my_list = []
    if sno == '000001':
        return jsonify(my_list)
    elif sno == '000000':
        return jsonify(my_list)
    else:
        db = conn_db()
        cursor = db.cursor()
        sql = "select * from staff where sno=%s and bno=%s and isexist='y'"
        rel = cursor.execute(sql, [sno, BRANCHNO])
        if rel > 0:
            row = cursor.fetchone()
            print(row)
            print(row[1])
            my_list = [{
                "sno": str(row[0]).zfill(6),
                "sname": row[1],
                "bno": row[2],
                "srole": row[3],
                "sex": row[4],
                "sphone": row[5],
                "joindate": row[6].strftime("%Y-%m-%d"),
                "spassword": row[7]
            }]
        db.close()
        cursor.close()
        return jsonify(my_list)


@app.route('/dele_staff', methods=['POST'])
def delestaff():
    db = conn_db()
    cursor = db.cursor()
    sno = request.get_json()['sno']
    print("dele_sno")
    print(sno)
    sql = "update staff set isexist = 'n' where sno=%s"
    cursor.execute(sql, sno)
    db.commit()
    db.close()
    cursor.close()
    return "success"


@app.route('/add_staff', methods=['POST'])
def addstaff():
    db = conn_db()
    cursor = db.cursor()
    form = request.get_json()['form']
    # print(type(form))
    # print(form["sname"])
    print("!!!" + form['joindate'])
    sql = "insert into staff(sname, bno, srole, sex, sphone, joindate, spassword) values (%s,%s,%s,%s,%s,%s,%s)"
    cursor.execute(sql, [form['sname'], form['bno'], form['srole'], form['sex'], form['sphone'], form['joindate'],
                         form['spassword']])
    db.commit()
    db.close()
    cursor.close()
    return "success"


@app.route('/update_staff', methods=['POST'])
def updatestaff():
    db = conn_db()
    cursor = db.cursor()
    staff = request.get_json()['staff']
    print(staff)
    name = staff["sname"]
    bno = staff["bno"]
    srole = staff["srole"]
    sex = staff["sex"]
    sphone = staff["sphone"]
    joindate = staff["joindate"]
    spassword = staff["spassword"]
    sno = staff["sno"]
    print(sno)
    sql = "update staff set sname = %s,bno=%s,srole=%s,sphone=%s,spassword=%s where sno=%s"
    cursor.execute(sql, [name, bno, srole, sphone, spassword, sno])
    db.commit()
    db.close()
    cursor.close()
    return "success"


if __name__ == '__main__':
    app.run(debug=True)
