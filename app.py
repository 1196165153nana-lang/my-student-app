# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import json

# -------------------------- 1. 安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# 复习周期配置
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "长难句"]
HOURS_OPTIONS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

# -------------------------- 2. 飞书 API 工具函数 --------------------------

def get_tenant_access_token():
    """获取飞书授权令牌"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}
    try:
        r = requests.post(url, headers=headers, json=payload)
        return r.json().get("tenant_access_token")
    except:
        return None

def fetch_feishu_data(table_id):
    """从飞书读取数据"""
    token = get_tenant_access_token()
    if not token: return pd.DataFrame()
    
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records?page_size=500"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        res_json = r.json()
        if res_json.get("code") != 0:
            st.error(f"读取失败: {res_json.get('msg')}")
            return pd.DataFrame()
        items = res_json.get("data", {}).get("items", [])
        return pd.DataFrame([item["fields"] for item in items]) if items else pd.DataFrame()
    except:
        return pd.DataFrame()

def add_feishu_record(table_id, fields):
    """向飞书写入一条记录"""
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json={"fields": fields})
    return r.json()

def generate_wechat_msg(name, review_date, learn_dates):
    """生成符合老师要求的微信复制文案"""
    rv_date_str = review_date.strftime("%m月%d日")
    # 对学习日期进行排序和格式化
    sorted_ln = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日学习内容") for d in sorted_ln])
    
    return f"""【21天抗遗忘复习提醒】

{rv_date_str}复习内容为：

{ln_dates_str}

请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦[加油][加油][加油]

也请家长把复习视频发到群里🌹"""

# -------------------------- 3. 界面布局 (手机端优化) --------------------------

st.set_page_config(page_title="21天抗遗忘管理系统", layout="centered", page_icon="🎯")

# 针对手机端增大按钮和文字
st.markdown("""
    <style>
    .stButton > button { width: 100%; height: 3.5em; font-size: 18px !important; }
    .stSelectbox label, .stDateInput label { font-size: 18px !important; font-weight: bold; }
    code { font-size: 16px !important; }
    </style>
    """, unsafe_allow_html=True)

today = datetime.date.today()

# 下拉菜单导航
menu = st.selectbox("📌 请选择功能模块", ["🔍 复习提醒查询", "📝 录入课时记录", "👤 学生库管理", "📊 历史数据总览", "📄 导出21天表"])

# -------------------------- 4. 各模块功能逻辑 --------------------------

# --- 模块 1：复习提醒查询 ---
if menu == "🔍 复习提醒查询":
    st.subheader("🔍 复习提醒查询")
    q_date = st.date_input("选择查询日期", today)
    
    with st.spinner('正在同步飞书云端任务...'):
        r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    
    # --- 新增：调试预览窗 (如果查不到，请点开这个看看) ---
    with st.expander("📊 检查云端原始数据"):
        if not r_df.empty:
            st.write("云端获取到的原始记录：")
            st.dataframe(r_df)
        else:
            st.warning("云端 records 表目前是空的，请确认录入是否成功，或飞书机器人是否有权限。")
    # -----------------------------------------------

    if not r_df.empty and "学习日期" in r_df.columns:
        # 🛠️ 关键修复：兼容飞书的“毫秒时间戳”和“字符串日期”
        try:
            # 先尝试按毫秒转换，如果失败（比如是字符串）则保持原样
            r_df['学习日期_dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
            # 如果转换后是空的（说明原本是字符串），则直接转换字符串
            mask = r_df['学习日期_dt'].isna()
            if mask.any():
                r_df.loc[mask, '学习日期_dt'] = pd.to_datetime(r_df.loc[mask, '学习日期']).dt.date
        except Exception as e:
            st.error(f"日期转换出错: {e}")
            r_df['学习日期_dt'] = pd.to_datetime(r_df['学习日期']).dt.date

        reminders = {}
        for _, row in r_df.iterrows():
            # 计算天数差：查询日期 - 学习日期 + 1
            # 比如 8月9日学习，8月9日查询，diff 应为 1 (第1天复习)
            days_diff = (q_date - row['学习日期_dt']).days + 1
            
            if days_diff in REVIEW_DAYS:
                name = row['姓名']
                if name not in reminders: reminders[name] = []
                # 记录原始日期字符串用于文案显示
                reminders[name].append(row['学习日期_dt'].strftime("%Y-%m-%d"))
        
        if reminders:
            st.error(f"🚨 今日共有 {len(reminders)} 位同学需复习")
            for name, dates in reminders.items():
                with st.container(border=True):
                    st.markdown(f"👤 **学员姓名：{name}**")
                    # 这里的 dates 已经是格式化好的字符串列表
                    msg = generate_wechat_msg(name, q_date, dates)
                    st.code(msg, language=None)
                    st.caption("✨ 点击右上角图标一键复制文案")
        else:
            st.info("💡 该日期暂无复习任务")
    else:
        st.info("💡 云端尚无课时记录，或飞书列名不匹配。")
# --- 模块 2：录入课时记录 ---
elif menu == "📝 录入课时记录":
    st.subheader("📝 课时录入")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    active_students = []
    if not s_df.empty and "状态" in s_df.columns:
        active_students = s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist()
    
    if not active_students:
        st.warning("⚠️ 请先去'学生库管理'添加在读学员")
    else:
        with st.form("lesson_form"):
            name = st.selectbox("👤 选择学生", active_students)
            date = st.date_input("📅 学习日期", today)
            content = st.selectbox("📚 学习内容", LEARN_CONTENTS)
            hour = st.select_slider("⏰ 课时数", options=HOURS_OPTIONS, value=1.0)
            
            if st.form_submit_button("💾 保存并同步到飞书"):
                # 🛠️ 关键修复：飞书日期字段需要 13 位毫秒时间戳
                timestamp = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                fields = {
                    "姓名": name,
                    "学习日期": timestamp,
                    "学习内容": content,
                    "课时": hour
                }
                res = add_feishu_record(TABLE_ID_RECORDS, fields)
                if res.get("code") == 0:
                    st.success(f"✅ 已存入飞书！学员：{name}")
                    st.balloons()
                else:
                    st.error(f"❌ 录入失败！")
                    st.json(res) # 显示报错细节，方便排查列名对错

# --- 模块 3：学生库管理 ---
elif menu == "👤 学生库管理":
    st.subheader("👥 学员信息库")
    with st.expander("➕ 添加新学员"):
        with st.form("student_form"):
            n_name = st.text_input("学生姓名")
            n_status = st.selectbox("初始状态", STATUS_OPTIONS)
            if st.form_submit_button("确认入库"):
                if n_name:
                    res = add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n_name, "状态": n_status})
                    if res.get("code") == 0:
                        st.success(f"✅ {n_name} 已入库")
                        st.rerun()
                    else:
                        st.error("入库失败，请检查飞书列名")
                        st.json(res)

    st.markdown("---")
    st.markdown("📊 **当前名册明细**")
    s_view = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_view.empty:
        # 如果有名册，显示出来，方便查看
        st.dataframe(s_view[["姓名", "状态"]], use_container_width=True)
    else:
        st.info("库中尚无学员信息")


# --- 模块 4：历史数据总览 ---
elif menu == "📊 历史数据总览":
    st.subheader("📊 历史记录（飞书实时同步）")
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        # 🛠️ 修复：将飞书的毫秒时间戳转为可读的日期格式
        if "学习日期" in all_r.columns:
            all_r['学习日期'] = pd.to_datetime(all_r['学习日期'], unit='ms', errors='coerce').dt.strftime('%Y-%m-%d')
        
        st.dataframe(all_r, use_container_width=True)
    else:
        st.info("尚无记录")
        
# --- 模块 5：导出21天表 ---
elif menu == "📄 导出21天表":
    st.subheader("📄 抗遗忘周期表导出")
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_all.empty:
        # 🛠️ 预处理：先把所有时间戳转为日期对象，方便后面计算
        r_all['学习日期_dt'] = pd.to_datetime(r_all['学习日期'], unit='ms', errors='coerce').dt.date
        
        names = r_all['姓名'].unique()
        target = st.selectbox("选择学生", names)
        
        if st.button("生成 21 天 CSV 表格"):
            # 筛选学生并按日期排序
            sub = r_all[r_all['姓名'] == target].sort_values("学习日期_dt")
            
            output = [
                ["21天抗遗忘周期记录表", "", "", "", "", "", "", "", "", "", "", "", ""],
                [f"学生姓名：{target}", "", "", "", "", "", "", "", "", "", "", "", ""],
                ["日期", "复习", "新学", "第1天", "第2天", "第3天", "第5天", "第7天", "第9天", "第12天", "第14天", "第17天", "第21天"]
            ]
            
            for _, row in sub.iterrows():
                ld = row['学习日期_dt']  # 这已经是日期对象了
                if pd.isna(ld): continue # 跳过空行
                
                # 计算10个复习日期
                rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                
                # 行内容：日期 | 复习(空) | 新学(空) | 10个计算出的日期
                row_content = [ld.strftime("%Y/%m/%d"), "", ""] + rvs
                output.append(row_content)
                output.append([""]*13) # 匹配你的模板，每行加个空行
            
            # 生成下载
            buf = io.StringIO()
            pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
            st.download_button(f"📥 下载 {target} 的表", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")
