# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import json
import time

# -------------------------- 1. 安全配置 (从 Secrets 读取) --------------------------
# 请确保已在 Streamlit Cloud 的 Settings -> Secrets 中配置以下所有字段
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# -------------------------- 2. 基础业务配置 --------------------------
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句"]
HOURS_OPTIONS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

# -------------------------- 3. 飞书 API 核心工具函数 --------------------------

def get_tenant_access_token():
    """获取飞书授权令牌"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}
    try:
        r = requests.post(url, headers=headers, json=payload)
        return r.json().get("tenant_access_token")
    except Exception:
        return None

def fetch_feishu_data(table_id):
    """从飞书读取多维表格数据"""
    token = get_tenant_access_token()
    if not token: return pd.DataFrame()
    
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records?page_size=500"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        res_json = r.json()
        items = res_json.get("data", {}).get("items", [])
        if not items: return pd.DataFrame()
        
        # 提取字段内容
        data = [item["fields"] for item in items]
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"读取云端失败: {e}")
        return pd.DataFrame()

def add_feishu_record(table_id, fields):
    """向飞书写入一条新记录"""
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json={"fields": fields})
        return r.json()
    except Exception as e:
        return {"code": -1, "msg": str(e)}

def generate_wechat_msg(name, review_date, learn_dates):
    """生成专业的21天抗遗忘微信文案"""
    rv_date_str = review_date.strftime("%m月%d日")
    # 转换日期格式并排序
    sorted_ln = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日学习内容") for d in sorted_ln])
    
    return f"""【21天抗遗忘复习提醒】

{rv_date_str}复习内容为：

{ln_dates_str}

请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦[加油][加油][加油]

也请家长把复习视频发到群里🌹"""

# -------------------------- 4. 界面自适应配置 --------------------------

st.set_page_config(page_title="21天抗遗忘云端专业版", layout="centered", page_icon="🎯")

# 适配手机的样式优化
st.markdown("""
    <style>
    .stButton > button { width: 100%; height: 3.5em; font-size: 18px !important; }
    .stSelectbox label, .stDateInput label { font-size: 16px !important; font-weight: bold; }
    code { font-size: 15px !important; line-height: 1.5; }
    div[data-testid="stExpander"] { border: 1px solid #ff4b4b; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

today = datetime.date.today()

# 顶层导航（手机端下拉菜单）
menu = st.selectbox("📌 切换功能模块", 
    ["🔍 复习提醒查询", "📝 录入课时记录", "👤 学生名单管理", "📊 历史数据总表", "📄 导出21天表", "📥 批量导入旧CSV"])

# -------------------------- 5. 功能模块实现 --------------------------

# --- 模块 1：复习提醒查询 ---
if menu == "🔍 复习提醒查询":
    st.subheader("🔍 复习提醒查询")
    
    with st.spinner('正在同步云端记录...'):
        r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    
    if not r_df.empty and "学习日期" in r_df.columns:
        # 处理日期转换（兼容时间戳和字符串）
        r_df['学习日期_dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
        mask = r_df['学习日期_dt'].isna()
        if mask.any():
            r_df.loc[mask, '学习日期_dt'] = pd.to_datetime(r_df.loc[mask, '学习日期']).dt.date
            
        col1, col2 = st.columns(2)
        with col1:
            q_date = st.date_input("选择查询日期", today)
        with col2:
            # 增加指定学生筛选
            all_names = ["全部学生"] + sorted(r_df['姓名'].unique().tolist())
            target_student = st.selectbox("筛选指定学生", all_names)

        reminders = {}
        for _, row in r_df.iterrows():
            # 计算天数差：查询日期 - 学习日期 + 1
            diff = (q_date - row['学习日期_dt']).days + 1
            if diff in REVIEW_DAYS:
                name = row['姓名']
                # 过滤指定学生
                if target_student != "全部学生" and name != target_student:
                    continue
                if name not in reminders: reminders[name] = []
                reminders[name].append(row['学习日期_dt'].strftime("%Y-%m-%d"))
        
        if reminders:
            st.error(f"🚨 今日共有 {len(reminders)} 位学员有任务")
            for name, dates in reminders.items():
                with st.container(border=True):
                    st.markdown(f"👤 **学生：{name}**")
                    msg = generate_wechat_msg(name, q_date, dates)
                    st.code(msg, language=None)
                    st.caption("✨ 点击右上角图标复制文案")
        else:
            st.info("💡 该日期暂无复习任务")
    else:
        st.info("💡 云端尚无课时记录，请先录入或导入。")

# --- 模块 2：录入课时记录 ---
elif menu == "📝 录入课时记录":
    st.subheader("📝 课时录入")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    active_students = []
    if not s_df.empty and "状态" in s_df.columns:
        active_students = s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist()
    
    if not active_students:
        st.warning("⚠️ 库中无在读学员，请先去'学生名单管理'录入。")
    else:
        with st.form("input_form"):
            name = st.selectbox("👤 选择学生", active_students)
            date = st.date_input("📅 学习日期", today)
            content = st.selectbox("📚 学习内容", LEARN_CONTENTS)
            hour = st.select_slider("⏰ 课时数", options=HOURS_OPTIONS, value=1.0)
            
            if st.form_submit_button("💾 保存并同步到云端"):
                # 飞书日期需转为13位毫秒时间戳
                ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                fields = {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour}
                res = add_feishu_record(TABLE_ID_RECORDS, fields)
                if res.get("code") == 0:
                    st.success(f"✅ 已存入飞书云端！")
                    st.balloons()
                else:
                    st.error(f"存入失败: {res.get('msg')}")

# --- 模块 3：学生名单管理 ---
elif menu == "👤 学生名单管理":
    st.subheader("👥 学生名单管理")
    with st.expander("➕ 添加新学员到信息库"):
        with st.form("add_student"):
            n_name = st.text_input("学生姓名")
            n_status = st.selectbox("当前状态", STATUS_OPTIONS)
            if st.form_submit_button("提交入库"):
                if n_name:
                    add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n_name, "状态": n_status})
                    st.success(f"✅ {n_name} 已成功入库")
                    st.rerun()

    st.markdown("---")
    st.write("📋 **当前名册明细**")
    s_view = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_view.empty:
        st.dataframe(s_view[["姓名", "状态"]], use_container_width=True)

# --- 模块 4：历史数据总表 ---
elif menu == "📊 历史数据总表":
    st.subheader("📊 历史明细 (云端同步)")
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        # 显示前先转换日期格式
        if "学习日期" in all_r.columns:
            all_r['学习日期'] = pd.to_datetime(all_r['学习日期'], unit='ms', errors='coerce').dt.strftime('%Y-%m-%d')
        st.dataframe(all_r, use_container_width=True)
    else:
        st.info("尚无记录")

# --- 模块 5：导出21天表 ---
elif menu == "📄 导出21天表":
    st.subheader("📄 单人21天记录表导出")
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_all.empty:
        r_all['日期对象'] = pd.to_datetime(r_all['学习日期'], unit='ms', errors='coerce').dt.date
        names = r_all['姓名'].unique()
        target = st.selectbox("选择学生", names)
        
        if st.button("生成 21 天表格"):
            sub = r_all[r_all['姓名'] == target].sort_values("日期对象")
            output = [
                ["21天抗遗忘周期记录表", "", "", "", "", "", "", "", "", "", "", "", ""],
                [f"学生姓名：{target}", "", "", "", "", "", "", "", "", "", "", "", ""],
                ["日期", "复习", "新学", "第1天", "第2天", "第3天", "第5天", "第7天", "第9天", "第12天", "第14天", "第17天", "第21天"]
            ]
            for _, row in sub.iterrows():
                ld = row['日期对象']
                if pd.isna(ld): continue
                rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"), "", ""] + rvs)
                output.append([""]*13)
            
            buf = io.StringIO()
            pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
            st.download_button(f"📥 下载 {target} 的表格", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")

# --- 模块 6：批量导入旧CSV ---
elif menu == "📥 批量导入旧CSV":
    st.subheader("📥 批量搬运旧数据到云端")
    st.info("本功能用于将您电脑里以前的 student_learning_records.csv 批量上传至飞书。")
    file = st.file_uploader("上传旧的 CSV 文件", type="csv")
    
    if file:
        old_df = pd.read_csv(file)
        st.write("📄 待导入数据预览 (前5条)：", old_df.head())
        
        if st.button(f"🚀 确认搬家：将 {len(old_df)} 条记录同步到飞书"):
            bar = st.progress(0)
            status = st.empty()
            count = 0
            for i, row in old_df.iterrows():
                try:
                    # 转换日期
                    ld = pd.to_datetime(row['学习日期']).date()
                    ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                    fields = {
                        "姓名": str(row['姓名']),
                        "学习日期": ts,
                        "学习内容": str(row['学习内容']),
                        "课时": float(row['课时'])
                    }
                    add_feishu_record(TABLE_ID_RECORDS, fields)
                    count += 1
                    bar.progress((i + 1) / len(old_df))
                    status.text(f"正在同步第 {count} 条：{row['姓名']}...")
                    # 飞书 API 频率限制保护
                    if count % 10 == 0: time.sleep(0.5)
                except Exception as e:
                    st.error(f"第 {i+1} 行导入出错: {e}")
            
            st.success(f"🎊 搬家大功告成！共成功同步 {count} 条数据。")
