# 북클라이밍 - 독서의 정상에 도전하라 – 2025-05-08
# rev.OCT-14: Reliable per-student query (no JOIN needed for exact id) + inputs normalization
import streamlit as st, requests, re, json, base64, time, mimetypes, uuid, datetime, random, os, io, sqlite3
import pandas as pd
from collections import Counter
from bs4 import BeautifulSoup
from openai import OpenAI

# ───── API 키 ─────
OPENAI_API_KEY       = st.secrets["OPENAI_API_KEY"]
NAVER_CLIENT_ID      = st.secrets["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET  = st.secrets["NAVER_CLIENT_SECRET"]
NAVER_OCR_SECRET     = st.secrets.get("NAVER_OCR_SECRET","")
client = OpenAI(api_key=OPENAI_API_KEY)

# ───── GitHub 설정(선택) ─────
GITHUB_TOKEN     = st.secrets.get("GITHUB_TOKEN",        "ghp_")
GH_REPO          = st.secrets.get("GH_REPO",             "ManseJang/bookclimbing")
GH_BRANCH        = st.secrets.get("GH_BRANCH",           "main")
GH_EVENTS_PATH   = st.secrets.get("GH_EVENTS_PATH",      "data/events.jsonl")
GH_STUDENTS_PATH = st.secrets.get("GH_STUDENTS_PATH",    "data/students.jsonl")

def _gh_enabled() -> bool:
    return bool(GITHUB_TOKEN and GITHUB_TOKEN != "ghp_" and GH_REPO and GH_BRANCH)

def _gh_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}

def _gh_contents_api(path:str)->str:
    return f"https://api.github.com/repos/{GH_REPO}/contents/{path}"

def gh_get_file_sha(path:str):
    try:
        r = requests.get(_gh_contents_api(path), headers=_gh_headers(),
                         params={"ref": GH_BRANCH}, timeout=10)
        if r.status_code == 200:
            return r.json().get("sha")
        return None
    except Exception:
        return None

def gh_append_jsonl(path:str, record:dict):
    if not _gh_enabled():
        return False, "GitHub sync disabled"
    sha = gh_get_file_sha(path)
    if sha:
        get_res = requests.get(_gh_contents_api(path), headers=_gh_headers(),
                               params={"ref": GH_BRANCH}, timeout=15)
        if get_res.status_code != 200:
            return False, f"GET failed: {get_res.status_code}"
        content_b64 = get_res.json().get("content","")
        try:
            raw = base64.b64decode(content_b64).decode("utf-8", errors="ignore")
        except Exception:
            raw = ""
        new_txt = (raw.rstrip("\n") + "\n" if raw else "") + json.dumps(record, ensure_ascii=False)
        b64 = base64.b64encode(new_txt.encode("utf-8")).decode()
        payload = {"message": f"Append JSONL: {os.path.basename(path)}",
                   "content": b64, "branch": GH_BRANCH, "sha": sha}
    else:
        new_txt = json.dumps(record, ensure_ascii=False) + "\n"
        b64 = base64.b64encode(new_txt.encode("utf-8")).decode()
        payload = {"message": f"Create JSONL: {os.path.basename(path)}",
                   "content": b64, "branch": GH_BRANCH}
    put_res = requests.put(_gh_contents_api(path), headers=_gh_headers(),
                           json=payload, timeout=20)
    return (put_res.status_code in (200,201), put_res.text[:200])

# ───── 유틸 ─────
def clean_html(t): return re.sub(r"<.*?>","",t or "")
def strip_fence(t): return re.sub(r"^```(json)?|```$", "", t.strip(), flags=re.M)
def gpt(msg,t=0.5,mx=800):
    return client.chat.completions.create(model="gpt-4.1",messages=msg,temperature=t,max_tokens=mx).choices[0].message.content.strip()
def to_data_url(url):
    while True:
        try:
            r=requests.get(url,timeout=5); r.raise_for_status()
            mime=r.headers.get("Content-Type") or mimetypes.guess_type(url)[0] or "image/jpeg"
            return f"data:{mime};base64,{base64.b64encode(r.content).decode()}"
        except Exception as e:
            st.warning(f"표지 다운로드 재시도… ({e})"); time.sleep(2)

# ───── 테마 ─────
FONT_SIZES = {"작게":"14px","보통":"16px","크게":"18px"}
def theme_css(font_px="16px"):
    return f"""
<style>
html {{ color-scheme: light !important; }}
:root{{ --bg:#f5f7fb; --sidebar-bg:#eef2f7; --card:#ffffff; --text:#0b1220; --ring:#e5e7eb;
--btn-bg:#fef08a; --btn-text:#0b1220; --btn-bg-hover:#fde047; --chip:#eef2ff; --chip-text:#1f2937; --fs-base:{font_px}; }}
html, body {{ background: var(--bg) !important; font-size: var(--fs-base); }}
section.main > div.block-container{{ background: var(--card); border-radius: 14px; padding: 18px 22px; box-shadow: 0 2px 16px rgba(0,0,0,.04); }}
h1,h2,h3,h4,h5{{ color:var(--text)!important; font-weight:800 }}
div[data-testid="stSidebar"]{{ background: var(--sidebar-bg)!important; border-right:1px solid var(--ring)!important; }}
.stButton>button, .stDownloadButton>button{{ background:var(--btn-bg)!important; color:var(--btn-text)!important; border-radius:12px!important;
  padding:10px 16px!important; font-weight:800!important; box-shadow:0 6px 16px rgba(0,0,0,.08)!important; transition:all .15s ease; }}
.stButton>button:hover{{ background:var(--btn-bg-hover)!important; transform:translateY(-1px) }}
.badge{{display:inline-block; padding:4px 10px; border-radius:999px; background:var(--chip); color:var(--chip-text); font-size:0.85rem;}}
</style>
"""

# ───── 안전 필터 ─────
ADULT_PATTERNS = [r"\b19\s*금\b","청소년\s*이용\s*불가","성인","야설","에로","포르노","노출","선정적","음란","야한","Adult","Erotic","Porn","R-?rated","BL\s*성인","성(관계|행위|묘사)","무삭제\s*판","금서\s*해제"]
BAD_WORDS = ["씨발","시발","병신","ㅄ","ㅂㅅ","좆","개새끼","새끼","좆같","ㅈ같","니애미","느금","개같","꺼져","죽어","염병","씹","sex","porn"]
ADULT_RE = re.compile("|".join(ADULT_PATTERNS), re.I)
BAD_RE   = re.compile("|".join(map(re.escape, BAD_WORDS)), re.I)
def is_adult_book(item:dict)->bool:
    if "adult" in item:
        try:
            if bool(item["adult"]): return True
        except: pass
    text=" ".join([clean_html(item.get("title","")), clean_html(item.get("author","")), clean_html(item.get("description","")), clean_html(item.get("publisher",""))])
    return bool(ADULT_RE.search(text))
def contains_bad_language(text:str)->bool: return bool(BAD_RE.search(text or ""))
def rewrite_polite(text:str)->str:
    try: return gpt([{"role":"user","content":f"다음 문장을 초등학생에게 어울리는 바르고 고운말로 바꿔줘. 의미는 유지하고 공격적 표현은 모두 제거:\n{text}"}],0.2,120)
    except: return "바르고 고운말을 사용해 다시 표현해 보세요."

# ───── NAVER Books & OCR ─────
def nv_search(q):
    hdr={"X-Naver-Client-Id":NAVER_CLIENT_ID,"X-Naver-Client-Secret":NAVER_CLIENT_SECRET}
    res=requests.get("https://openapi.naver.com/v1/search/book.json",headers=hdr,params={"query":q,"display":10}).json().get("items",[])
    return [b for b in res if not is_adult_book(b)]
def crawl_syn(title):
    try:
        hdr={"User-Agent":"Mozilla/5.0"}
        soup=BeautifulSoup(requests.get(f"https://book.naver.com/search/search.nhn?query={title}",headers=hdr,timeout=8).text(),"html.parser")
        f=soup.select_one("ul.list_type1 li a")
        if not f: return ""
        intro=BeautifulSoup(requests.get("https://book.naver.com"+f["href"],headers=hdr,timeout=8).text(),"html.parser").find("div","book_intro")
        return intro.get_text("\n").strip() if intro else ""
    except: return ""
def synopsis(title,b):
    d=clean_html(b.get("description","")); c=crawl_syn(title); return (d+"\n\n"+c).strip() if (d or c) else ""
def elem_syn(title,s,level):
    detail={"쉬움":"초등 저학년, 12~16문장","기본":"초등 중학년, 16~20문장","심화":"초등 고학년, 18~22문장(배경·인물 감정·주제 의식 포함)"}[level]
    return gpt([{"role":"user","content":f"아래 원문만 근거로 책 '{title}'의 줄거리를 {detail}로 **3단락** 자세히 써줘. (배경/인물/갈등/결말·주제 포함)\n\n원문:\n{s}"}],0.32,3200)
def nv_ocr(img):
    url=st.secrets.get("NAVER_CLOVA_OCR_URL")
    if not url or not NAVER_OCR_SECRET: return "(OCR 설정 필요)"
    payload={"version":"V2","requestId":str(uuid.uuid4()),"timestamp":int(datetime.datetime.utcnow().timestamp()*1000),
             "images":[{"name":"img","format":"jpg","data":base64.b64encode(img).decode()}]}
    res=requests.post(url,headers={"X-OCR-SECRET":NAVER_OCR_SECRET,"Content-Type":"application/json"},json=payload,timeout=30).json()
    try: return " ".join(f["inferText"] for f in res["images"][0]["fields"])
    except: return "(OCR 파싱 오류)"

# ───── 퀴즈 생성 보조 ─────
def make_quiz(raw:str)->list:
    m=re.search(r"\[.*]", strip_fence(raw), re.S)
    if not m: return []
    try: arr=json.loads(m.group())
    except json.JSONDecodeError: return []
    quiz=[]
    for it in arr:
        if isinstance(it,str):
            try: it=json.loads(it)
            except: continue
        if "answer" in it and "correct_answer" not in it: it["correct_answer"]=it.pop("answer")
        if not {"question","options","correct_answer"}.issubset(it.keys()): continue
        opts=it["options"][:]
        if len(opts)!=4: continue
        correct_txt = (opts[it["correct_answer"]-1] if isinstance(it["correct_answer"],int) else str(it["correct_answer"]).strip())
        random.shuffle(opts)
        if correct_txt not in opts: opts[0]=correct_txt
        quiz.append({"question":it["question"],"options":opts,"correct_answer":opts.index(correct_txt)+1})
    return quiz if len(quiz)==5 else []

# ───── 난이도 파라미터 ─────
def level_params(level:str):
    if level=="쉬움": return dict(temp=0.25, explain_len=900, debate_rounds=4, language="아주 쉬운 말", penalties=False)
    if level=="심화": return dict(temp=0.5, explain_len=1700, debate_rounds=6, language="정확하고 논리적인 말", penalties=True)
    return dict(temp=0.35, explain_len=1300, debate_rounds=6, language="친절한 말", penalties=False)

# ───── 이미지 유틸 ─────
def load_intro_path():
    for name in ["asset/intro.png","asset/intro.jpg","asset/intro.jpeg","asset/intro.webp"]:
        if os.path.exists(name): return name
    return None
def render_img_percent(path:str, percent:float=0.7):
    with open(path,"rb") as f: b64=base64.b64encode(f.read()).decode()
    mime=mimetypes.guess_type(path)[0] or "image/png"
    st.markdown(f'<p style="text-align:center;"><img src="data:{mime};base64,{b64}" style="width:{int(percent*100)}%; border-radius:12px;"/></p>',unsafe_allow_html=True)

# ───── 토론 주제 추천 ─────
def _normalize_topic_form(s: str, prefer_ought: bool = False) -> str:
    s = (s or "").strip()
    s = re.sub(r"[?？]+$", "", s)
    s = re.sub(r"(인가요|일까요|맞을까요|좋을까요|될까요|될까|요)$", "", s).strip()
    if "옳" in s or "것이 옳" in s:
        s = re.sub(r"(옳[^\s\.\)]*)$", "옳다", s)
        if not s.endswith("옳다."): s = s.rstrip(".") + "옳다."
        return s
    if not s.endswith("해야 한다.") and not s.endswith("하는 것이 옳다."):
        s = s.rstrip(".") + (" 하는 것이 옳다." if prefer_ought else " 해야 한다.")
    return s

def recommend_topics(title, syn, level, avoid:list, tries=2):
    base_prompt=(f"너는 초등 독서토론 교사야. 아래 책 '{title}'의 줄거리를 바탕으로 토론 주제 2개를 추천."
                 f" 각 주제는 '…해야 한다.' 또는 '…하는 것이 옳다.'로 끝나는 문장. JSON 배열만.\n\n줄거리:\n{syn[:1600]}")
    for _ in range(tries):
        raw = gpt([{"role":"user","content":base_prompt}], t=0.5, mx=360)
        try:
            arr = [clean_html(x).strip() for x in json.loads(strip_fence(raw)) if isinstance(x, str)]
        except:
            arr = []
        if len(arr) >= 2:
            return [_normalize_topic_form(arr[0], False), _normalize_topic_form(arr[1], True)]
    return ["약속을 지켜야 한다.", "힘들 때 도움을 요청하는 것이 옳다."]

# ───── 관련 낱말 ─────
def related_words(word:str, level:str)->dict:
    prompt=(f"단어 '{word}' 관련 낱말을 초등 {level} 수준으로 JSON만 출력:"
            "{\"meaning\":\"쉬운뜻1문장\",\"synonyms\":[5~8],\"antonyms\":[5~8],\"examples\":[\"문장1\",\"문장2\"]}")
    raw=gpt([{"role":"user","content":prompt}],0.25,360)
    try:
        data=json.loads(strip_fence(raw))
        data["meaning"]=str(data.get("meaning","")).strip()
        data["synonyms"]=[str(x).strip() for x in data.get("synonyms",[])]
        data["antonyms"]=[str(x).strip() for x in data.get("antonyms",[])]
        data["examples"]=[str(x).strip() for x in data.get("examples",[])]
        return data
    except:
        return {"meaning":"(설명 생성 실패)","synonyms":[],"antonyms":[],"examples":[]}

# ───── TXT 생성 ─────
def build_debate_txt_bytes(title:str, topic:str, user_side:str, transcript:list, score:dict, feedback_text:str):
    txt="독서토론 기록\n\n"
    txt+=f"[책] {title}\n[주제] {topic}\n[학생 입장] {user_side}\n\n"
    if score:
        txt+=f"[점수] 찬성 {score.get('pro',{}).get('total','-')}점 / 반대 {score.get('con',{}).get('total','-')}점, 승리: {score.get('winner','-')}\n\n"
    txt+="[총평]\n"+(feedback_text or "")+"\n\n[토론 로그]\n"+"\n".join(transcript)
    return txt.encode("utf-8"), "text/plain", "debate_record.txt"

# ───── 데이터 (SQLite) ─────
DB_PATH = "classdb.db"
def _sqlite_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS students(
        student_id TEXT PRIMARY KEY,
        year INT, school TEXT, grade INT, klass INT, number INT,
        created_at TEXT, name TEXT
    );""")
    conn.execute("""CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT, ts TEXT, page TEXT, payload TEXT
    );""")
    conn.commit()
    return conn

def _ensure_student_row(student_id:str, year:int, school:str, grade:int, klass:int, number:int, name:str):
    conn = _sqlite_conn()
    cur = conn.execute("SELECT 1 FROM students WHERE student_id=?", (student_id,))
    if cur.fetchone() is None:
        conn.execute("""INSERT OR IGNORE INTO students(student_id, year, school, grade, klass, number, name, created_at)
                        VALUES (?,?,?,?,?,?,?,?)""",
                     (student_id, year, school, grade, klass, number, name, datetime.datetime.now().isoformat()))
        conn.commit()
    conn.close()

def db_insert_student(student_id, year, school, grade, klass, number, name):
    try:
        conn = _sqlite_conn()
        conn.execute("""INSERT OR REPLACE INTO students(student_id, year, school, grade, klass, number, name, created_at)
                        VALUES (?,?,?,?,?,?,?,?)""",
                     (student_id, year, school, grade, klass, number, name, datetime.datetime.now().isoformat()))
        conn.commit(); conn.close()
    except Exception as e:
        st.warning(f"학생 저장 오류: {e}")

def db_save_event(student_id, page, payload_dict):
    try:
        conn = _sqlite_conn()
        conn.execute("INSERT INTO events(student_id, ts, page, payload) VALUES (?,?,?,?)",
                     (student_id, datetime.datetime.now().isoformat(), page, json.dumps(payload_dict,ensure_ascii=False)))
        conn.commit(); conn.close()
    except Exception as e:
        st.warning(f"기록 저장 오류: {e}")

# ── (중요 수정) 대시보드 조회: 정확히 지정되면 events를 student_id로 직접 검색
def db_dashboard(year=None, school=None, grade=None, klass=None, number=None):
    school = (school or "").strip()
    conn = _sqlite_conn()

    # 모든 키가 “개별 학생”으로 명확하면: events만 조회
    if year and school and grade not in (None, 0) and klass not in (None, 0) and number not in (None, 0):
        sid = f"{int(year)}-{school}-{int(grade)}-{int(klass)}-{int(number)}"
        rows = conn.execute("""SELECT e.ts, e.page, e.payload, e.student_id
                               FROM events e WHERE e.student_id=? ORDER BY e.ts ASC""", (sid,)).fetchall()
        conn.close()
        data=[]
        for ts,page,payload,sid in rows:
            try: d=json.loads(payload)
            except: d={"_raw":payload}
            # 개별 학생 메타는 sid에서 역파싱
            _, sc, gr, kl, no = sid.split("-", 4)
            data.append({"ts":ts,"year":year,"school":sc,"grade":int(gr),"klass":int(kl),
                         "number":int(no),"page":page,"payload":d,"student_id":sid})
        return pd.DataFrame(data)

    # 집계 모드: 기존 JOIN으로 넓게 조회
    q = """SELECT s.year, s.school, s.grade, s.klass, s.number, e.page, e.payload, e.ts, s.student_id
           FROM events e JOIN students s ON e.student_id=s.student_id WHERE 1=1"""
    params=[]
    if year:   q+=" AND s.year=?";   params.append(year)
    if school: q+=" AND s.school=?"; params.append(school)
    if grade is not None and grade!=0:  q+=" AND s.grade=?";  params.append(grade)
    if klass is not None and klass!=0:  q+=" AND s.klass=?";  params.append(klass)
    if number is not None and number!=0:q+=" AND s.number=?"; params.append(number)
    q+=" ORDER BY e.ts ASC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    data=[]
    for y,sc,gr,kl,no,page,payload,ts,sid in rows:
        try: d=json.loads(payload)
        except: d={"_raw":payload}
        data.append({"ts":ts,"year":y,"school":sc,"grade":gr,"klass":kl,"number":no,
                     "page":page,"payload":d,"student_id":sid})
    return pd.DataFrame(data)

# ───── 저장 래퍼 (정규화 포함) ─────
def _norm_school(s:str)->str:
    return (s or "").strip()

def save_student(year:int, school:str, grade:int, klass:int, number:int, name:str):
    school = _norm_school(school)
    student_id = f"{int(year)}-{school}-{int(grade)}-{int(klass)}-{int(number)}"
    db_insert_student(student_id, year, school, grade, klass, number, name or "")
    st.session_state.update(dict(student_id=student_id, year=year, school=school,
                                 grade=grade, klass=klass, number=number, name=name))
    st.toast(f"학생 저장 완료: {student_id}" + (f" ({name})" if name else ""), icon="✅")

def save_event(page:str, payload:dict):
    year  = int(st.session_state.get("year", datetime.datetime.now().year))
    school= _norm_school(st.session_state.get("school",""))
    grade = int(st.session_state.get("grade",0))
    klass = int(st.session_state.get("klass",0))
    number= int(st.session_state.get("number",0))
    sid = st.session_state.get("student_id") or f"{year}-{school}-{grade}-{klass}-{number}"
    st.session_state.student_id = sid  # 고정

    _ensure_student_row(sid, year, school, grade, klass, number, st.session_state.get("name",""))
    db_save_event(sid, page, payload)
    st.toast(f"기록 저장: {page}", icon="💾")

# ───── 추천 도서 ─────
def fetch_grade_recs(grade:int):
    qs = [f"초등 {grade}학년 동화 추천", f"초등 {grade}학년 소설 추천"]
    seen = set(); out=[]
    for q in qs:
        for b in nv_search(q):
            key = clean_html(b.get("title","")).strip()
            if key and key not in seen:
                seen.add(key); out.append(b)
    return out[:5]

def select_book_and_build(sel):
    st.session_state.selected_book=sel
    title=clean_html(sel["title"])
    base_syn=synopsis(title,sel)
    st.session_state.synopsis=elem_syn(title,base_syn,st.session_state.level)
    st.success(f"책 선택 완료! → {title}")
    save_event("book",{
        "title": title,
        "author": clean_html(sel.get("author","")),
        "level": st.session_state.level
    })

def render_reco_table(items:list):
    h1,h2,h3 = st.columns([1,2,5])
    with h1: st.markdown("**표지**")
    with h2: st.markdown("**책 제목**")
    with h3: st.markdown("**책 내용**")
    st.markdown("<div style='height:8px;border-bottom:1px solid #e5e7eb;'></div>", unsafe_allow_html=True)
    for i,b in enumerate(items):
        img = b.get("image") or ""
        title = clean_html(b.get("title",""))
        desc = clean_html(b.get("description","")).strip()
        if not desc:
            brief = (crawl_syn(title) or "").strip()
            desc = brief[:180]
        if len(desc)>180: desc = desc[:170]+"…"
        c1,c2,c3 = st.columns([1,2,5])
        with c1:
            if img: st.image(img, use_container_width=True)
        with c2:
            st.markdown(f"**{title}**")
            author = clean_html(b.get("author",""))
            if author: st.caption(author)
        with c3:
            st.markdown(desc or "(소개 없음)")
            if st.button("✅ 이 책 선택", key=f"reco_pick_{i}"):
                select_book_and_build(b)
                st.rerun()
        st.markdown("<div style='height:8px;border-bottom:1px dashed #e5e7eb;'></div>", unsafe_allow_html=True)

# ───── 학생 패널 ─────
def student_panel():
    if "ui_font_size_choice" not in st.session_state:
        st.session_state["ui_font_size_choice"] = "보통"

    st.markdown("#### 🅰️ 글씨 크기")
    st.radio("글씨 크기 선택", ["작게","보통","크게"],
             key="ui_font_size_choice", horizontal=True, label_visibility="collapsed")
    st.divider()

    st.markdown("#### 👤 학생 정보")
    with st.form("student_form"):
        col1, col2 = st.columns(2)
        with col1:
            year  = st.number_input("학년도", min_value=2020, max_value=2100, value=int(st.session_state.get("year", datetime.datetime.now().year)), step=1)
            school= st.text_input("학교", value=_norm_school(st.session_state.get("school","")))
            grade = st.number_input("학년", min_value=1, max_value=6, value=int(st.session_state.get("grade",3)), step=1)
        with col2:
            klass = st.number_input("반", min_value=1, max_value=20, value=int(st.session_state.get("klass",1)), step=1)
            number= st.number_input("번호", min_value=1, max_value=50, value=int(st.session_state.get("number",1)), step=1)
            name  = st.text_input("이름(선택)", value=st.session_state.get("name",""))
        submitted = st.form_submit_button("학생 사용/저장")
        if submitted:
            save_student(int(year), _norm_school(school), int(grade), int(klass), int(number), name)

    # GitHub 상태 배지(선택)
    if _gh_enabled():
        st.markdown("<span class='badge'>GitHub 동기화: 활성</span>", unsafe_allow_html=True)

# ───── PAGE 1 : 책검색 & 표지대화 ─────
def page_book():
    st.markdown('<span class="badge">난이도(모든 활동 적용)</span>', unsafe_allow_html=True)
    level = st.selectbox("난이도", ["쉬움","기본","심화"], index=["쉬움","기본","심화"].index(st.session_state.get("level","기본")))
    st.session_state.level = level

    intro_path=load_intro_path()
    if intro_path:
        l,c,r=st.columns([0.15,0.70,0.15]); 
        with c: render_img_percent(intro_path,0.70)

    st.header("📘 1) 책 찾기 & 표지 이야기")
    if st.sidebar.button("활동 다시하기"): st.session_state.clear(); st.rerun()

    # ── 이달의 추천 도서
    rec_col, _ = st.columns([1,3])
    with rec_col:
        if st.button("🎁 이달의 추천 도서"):
            st.session_state["show_reco"]= not st.session_state.get("show_reco", False)

    if st.session_state.get("show_reco", False):
        st.markdown("#### 이달의 추천 도서 (3~6학년 · 동화/소설)")
        default_grade = min(max(int(st.session_state.get("grade",3)),3),6)
        g = st.selectbox("학년 선택", options=[3,4,5,6], index=[3,4,5,6].index(default_grade))
        c1,c2 = st.columns([1,4])
        with c1:
            if st.button("🔎 추천 불러오기"):
                st.session_state["reco"] = fetch_grade_recs(int(g))
        items = st.session_state.get("reco", [])
        if items:
            render_reco_table(items)
        else:
            st.info("추천 결과가 없어요. [🔎 추천 불러오기]를 눌러 주세요.")

    # ── 일반 검색
    q=st.text_input("책 제목·키워드")
    if st.button("🔍 검색") and q.strip():
        result=nv_search(q.strip())
        if not result: st.warning("검색 결과가 없거나(또는 안전 필터에 의해) 숨김 처리되었습니다.")
        st.session_state.search=result

    if bs:=st.session_state.get("search"):
        _, sel=st.selectbox("책 선택",[(f"{clean_html(b['title'])} | {clean_html(b['author'])}",b) for b in bs],format_func=lambda x:x[0])
        if st.button("✅ 선택"):
            select_book_and_build(sel)

    if bk:=st.session_state.get("selected_book"):
        title=clean_html(bk["title"]); cover=bk["image"]; syn=st.session_state.synopsis
        st.subheader("📖 줄거리"); st.write(syn or "(줄거리 없음)")
        lc,rc=st.columns([1,1])
        with lc: st.image(cover,caption=title,use_container_width=True)
        with rc:
            st.markdown("### 🖼️ 표지 챗봇 (독서 전 활동)")
            if "chat" not in st.session_state:
                st.session_state.chat=[
                    {"role":"system","content":f"초등 대상 표지 대화 챗봇. 난이도:{st.session_state.level}. {level_params(st.session_state.level)['language']}로 질문해요."},
                    {"role":"user","content":[{"type":"text","text":"표지입니다."},{"type":"image_url","image_url":{"url":to_data_url(cover)}}]},
                    {"role":"assistant","content":"책 표지에서 가장 먼저 보이는 것은 무엇인가요?"}]
            for m in st.session_state.chat:
                if m["role"]=="assistant": st.chat_message("assistant").write(m["content"])
                elif m["role"]=="user" and isinstance(m["content"],str): st.chat_message("user").write(m["content"])
            if u:=st.chat_input("답/질문 입력…"):
                if contains_bad_language(u):
                    st.warning("바르고 고운말을 사용해 주세요. 아래처럼 바꿔 볼까요?"); st.info(rewrite_polite(u))
                else:
                    st.session_state.chat.append({"role":"user","content":u})
                    rsp=gpt(st.session_state.chat,level_params(st.session_state.level)['temp'],400)
                    st.session_state.chat.append({"role":"assistant","content":rsp}); st.rerun()

        if st.button("다음 단계 ▶ 2) 낱말 탐정"):
            st.session_state.current_page="단어 알아보기"; st.rerun()

# ───── PAGE 2 : 단어 알아보기 ─────
def page_vocab():
    st.header("🧩 2) 낱말 탐정")
    if "selected_book" not in st.session_state:
        st.info("책을 먼저 선택해주세요."); 
        if st.button("◀ 이전 (1)"): st.session_state.current_page="책 검색"; st.rerun()
        return
    title=clean_html(st.session_state.selected_book["title"])
    st.markdown(f"**책 제목:** {title}  &nbsp;&nbsp; <span class='badge'>난이도: {st.session_state.level}</span>", unsafe_allow_html=True)

    word = st.text_input("궁금한 단어", value=st.session_state.get("word",""))
    if st.button("🧠 단어 알아보기"):
        if not word.strip(): st.warning("단어를 입력하세요.")
        elif contains_bad_language(word):
            st.warning("바르고 고운말을 사용해 주세요 😊"); st.info(rewrite_polite(word))
        else:
            req=(f"초등학생 {st.session_state.level} 수준으로 '{word}'를 설명해줘. "
                 f"1) 쉬운 뜻 1줄  2) 사용 예시 2가지(각 1문장). 어려운 한자어는 쉬운 말로.")
            st.session_state.vocab_meaning = gpt([{"role":"user","content":req}],0.3,380)
            st.session_state.rel_out = related_words(word, st.session_state.level)
            st.session_state.word = word

    if st.session_state.get("vocab_meaning"):
        st.markdown("#### 뜻과 예시")
        st.write(st.session_state.vocab_meaning); st.divider()

    if st.session_state.get("rel_out"):
        rel=st.session_state.rel_out
        st.markdown("#### 관련있는 낱말", unsafe_allow_html=True)
        cL, cR = st.columns(2)
        with cL:
            st.markdown("**비슷한 말(동의어)**")
            st.write(", ".join(rel.get("synonyms",[])) or "(없음)")
        with cR:
            st.markdown("**반대되는 말(반의어)**")
            st.write(", ".join(rel.get("antonyms",[])) or "(없음)")
        st.markdown("**쉬운 설명**")
        st.write(rel.get("meaning",""))
        if rel.get("examples"):
            st.markdown("**예문**")
            for ex in rel["examples"]: st.write("- " + ex)

    if st.button("다음 단계 ▶ 3) 이야기 퀴즈"):
        st.session_state.current_page="독서 퀴즈"; st.rerun()

# ───── PAGE 3 : 퀴즈 ─────
def page_quiz():
    st.header("📝 3) 이야기 퀴즈")
    if "selected_book" not in st.session_state:
        st.info("책을 먼저 선택해주세요.");
        if st.button("◀ 이전 (1)"): st.session_state.current_page="책 검색"; st.rerun()
        return
    if st.sidebar.button("퀴즈 초기화"): st.session_state.pop("quiz",None); st.session_state.pop("answers",None); st.rerun()
    title=clean_html(st.session_state.selected_book["title"]); syn=st.session_state.synopsis
    st.markdown(f"**책 제목:** {title}  &nbsp;&nbsp; <span class='badge'>난이도: {st.session_state.level}</span>", unsafe_allow_html=True)
    lv=st.session_state.level; lvp=level_params(lv)

    if "ans_uid" not in st.session_state: st.session_state.ans_uid = 0
    uid = st.session_state.ans_uid

    if "quiz" not in st.session_state and st.button("🧠 퀴즈 생성"):
        style={"쉬움":"쉽고 명확, 지문 그대로","기본":"핵심 사건 이해","심화":"추론/관계"}[lv]
        raw=gpt([{"role":"user","content":f"책 '{title}' 줄거리 기반 5문항 4지선다 JSON. question/options(4)/correct_answer(1~4). 난이도:{lv}, 스타일:{style}. 정답 번호 분포 고르게.\n\n줄거리:\n{syn}"}],lvp['temp'],900)
        q=make_quiz(raw)
        if q: st.session_state.quiz=q
        else: st.error("형식 오류, 다시 생성"); st.code(raw)

    if q:=st.session_state.get("quiz"):
        if "answers" not in st.session_state: st.session_state.answers={}
        for i,qa in enumerate(q):
            st.markdown(f"**문제 {i+1}.** {qa['question']}")
            pick=st.radio("",qa["options"],index=None,key=f"ans-{uid}-{i}")
            if pick is not None:
                st.session_state.answers[i]=qa["options"].index(pick)+1
        c1,c2=st.columns([1,1])
        with c1:
            if st.button("📊 채점"):
                miss=[i+1 for i in range(5) if i not in st.session_state.answers]
                if miss: st.error(f"{miss}번 문제 선택 안함"); return
                correct=[st.session_state.answers[i]==q[i]["correct_answer"] for i in range(5)]
                score=sum(correct)*20
                st.subheader("결과")
                for i,ok in enumerate(correct,1):
                    st.write(f"문제 {i}: {'⭕' if ok else '❌'} (정답: {q[i-1]['options'][q[i-1]['correct_answer']-1]})")
                st.write(f"**총점: {score} / 100**")
                guide="아주 쉽게" if lv=="쉬움" else ("근거 인용과 함께" if lv=="심화" else "핵심 이유 중심")
                explain=gpt([{"role":"user","content":"다음 JSON으로 각 문항 해설과 총평을 한국어로 작성. 난이도:"+lv+" "+guide+".\n"+json.dumps({"quiz":q,"student_answers":st.session_state.answers},ensure_ascii=False)}],lvp['temp'],lvp['explain_len'])
                st.write(explain)
                save_event("quiz", {"title": title, "score": score, "correct": correct, "level": st.session_state.level})
        with c2:
            if st.button("🔁 다시 도전하기"):
                st.session_state.answers={}
                st.session_state.ans_uid = uid + 1
                st.rerun()

    if st.button("다음 단계 ▶ 4) 독서 생각 나누기"):
        st.session_state.current_page="독서 토론"; st.rerun()

# ───── PAGE 4 : 독서 토론 ─────
def page_discussion():
    st.header("🗣️ 4) 독서 생각 나누기")
    if "selected_book" not in st.session_state:
        st.info("책을 먼저 선택해주세요.");
        if st.button("◀ 이전 (1)"): st.session_state.current_page="책 검색"; st.rerun()
        return
    if st.sidebar.button("토론 초기화"):
        for k in ("debate_started","debate_round","debate_chat","debate_topic","debate_eval","user_side","bot_side","topics","topic_choice","score_json","user_feedback_text"): st.session_state.pop(k,None); st.rerun()

    title=clean_html(st.session_state.selected_book["title"]); syn=st.session_state.synopsis
    st.markdown(f"**책 제목:** {title}  &nbsp;&nbsp; <span class='badge'>난이도: {st.session_state.level}</span>", unsafe_allow_html=True)
    lv=st.session_state.level; lvp=level_params(lv)

    if st.button("🎯 토론 주제 추천 2가지"):
        hist = st.session_state.get("topic_history", {})
        avoid = list(hist.get(title, []))
        topics = recommend_topics(title, syn, lv, avoid)
        st.session_state.topics = topics
        hist.setdefault(title, set()).update(topics)
        st.session_state.topic_history = hist

    if tp:=st.session_state.get("topics"):
        st.subheader("추천 주제 선택")
        choice=st.radio("토론 주제", tp+["(직접 입력)"], index=0, key="topic_choice")
    else:
        choice=st.radio("토론 주제", ["(직접 입력)"], index=0, key="topic_choice")
    topic=st.text_input("직접 입력", value=st.session_state.get("debate_topic","")) if choice=="(직접 입력)" else choice
    side=st.radio("당신은?",("찬성","반대"))
    b1,b2=st.columns([1,1])
    with b1: start_clicked=st.button("🚀 토론 시작")
    with b2:
        if st.button("다음 단계 ▶ 5) 독서 생각 성찰하기"): st.session_state.current_page="독서 감상문 피드백"; st.rerun()

    if start_clicked:
        if not topic or not topic.strip(): st.warning("토론 주제를 입력하거나 선택해주세요.")
        else:
            rounds=lvp['debate_rounds']; order={4:[1,2,3,4],6:[1,2,3,4,5,6]}[rounds]
            st.session_state.update({
                "debate_started":True,"debate_round":1,"debate_topic":topic,
                "user_side":side,"bot_side":"반대" if side=="찬성" else "찬성","debate_order":order,
                "debate_chat":[{"role":"system","content":f"초등 독서토론 진행자. 모든 발언은 반드시 책의 줄거리 근거. 난이도:{lv}, 어조:{lvp['language']}. 주제 '{topic}'. 1찬성입론 2반대입론 3찬성반론 4반대반론"+("" if len(order)==4 else " 5찬성최후 6반대최후")+f". 근거는 다음 줄거리에서만:\n{syn[:1200]}"}]
            }); st.rerun()

    if st.session_state.get("debate_started"):
        lbl={1:"찬성측 입론",2:"반대측 입론",3:"찬성측 반론",4:"반대측 반론",5:"찬성측 최후 변론",6:"반대측 최후 변론"}
        for m in st.session_state.debate_chat:
            if m["role"]=="assistant": st.chat_message("assistant").write(str(m["content"]))
            elif m["role"]=="user": st.chat_message("user").write(str(m["content"]))
        rd=st.session_state.debate_round; order=st.session_state.debate_order
        if rd<=len(order):
            step=order[rd-1]
            st.markdown(f"### 현재: {lbl[step]}")
            user_turn=((step%2==1 and st.session_state.user_side=="찬성") or (step%2==0 and st.session_state.user_side=="반대"))
            if user_turn:
                txt = st.chat_input("내 발언")
                if txt:
                    if contains_bad_language(txt):
                        st.warning("바르고 고운말을 사용해 주세요. 아래처럼 바꿔 볼까요?"); st.info(rewrite_polite(txt))
                    else:
                        st.session_state.debate_chat.append({"role":"user","content":f"[{lbl[step]}] {txt}"})
                        st.session_state.debate_round+=1; st.rerun()
            else:
                convo=st.session_state.debate_chat+[{"role":"user","content":f"[{lbl[step]}]"}]
                bot=gpt(convo,level_params(st.session_state.level)['temp'],420)
                st.session_state.debate_chat.append({"role":"assistant","content":bot})
                st.session_state.debate_round+=1; st.rerun()
        else:
            if "debate_eval" not in st.session_state:
                transcript=[]
                for m in st.session_state.debate_chat:
                    if m["role"]=="user": transcript.append(f"STUDENT({st.session_state.user_side}): {m['content']}")
                    elif m["role"]=="assistant": transcript.append(f"BOT({st.session_state.bot_side}): {m['content']}")
                score_prompt=("아래는 초등학생과 챗봇의 찬반 토론 대화입니다.\n각 측에 대해 5가지 기준을 0~20점으로 채점, 총점 100점.\n"
                              "기준: 1줄거리 이해 2생각을 분명히 말함(책과 연결) 3근거 제시 4질문에 답하고 잇기 5새로운 질문/깊이.\n"
                              f"학생(STUDENT)은 '{st.session_state.user_side}', BOT은 '{st.session_state.bot_side}'. JSON만:\n"
                              "{{\"pro\":{{\"criteria_scores\":[..5..],\"total\":정수}},\"con\":{{\"criteria_scores\":[..5..],\"total\":정수}},\"winner\":\"찬성|반대\"}}")
                res_score=gpt([{"role":"user","content":"\n".join(transcript)+"\n\n"+score_prompt}],0.2,800)
                try: st.session_state.score_json=json.loads(strip_fence(res_score))
                except: st.session_state.score_json={"pro":{"total":0},"con":{"total":0},"winner":"-"}
                my_lines=[m["content"] for m in st.session_state.debate_chat if m["role"]=="user" and "[" in m["content"]]
                other_lines=[m["content"] for m in st.session_state.debate_chat if m["role"]=="assistant"]
                fb_prompt=(f"너는 초등 토론 코치야. 아래 '학생 발언'만 근거로 서술형 피드백을 써줘. 챗봇 발언은 참고만.\n"
                           "구성: ① 총평 ② 잘한 점 ③ 더 나아질 점 ④ 다음 토론 팁(행동문장). 쉬운 말 사용.\n\n"
                           f"[학생 측:{st.session_state.user_side}] 발언:\n" + "\n".join(my_lines[:50]) +
                           "\n\n(참고) 상대 발언:\n" + "\n".join(other_lines[:50]) +
                           "\n\n토론의 근거가 된 줄거리:\n" + st.session_state.synopsis[:1200])
                st.session_state.user_feedback_text=gpt([{"role":"user","content":fb_prompt}],0.3,1200)
                sc=st.session_state.score_json
                save_event("debate",{
                    "title": title, "topic": st.session_state.debate_topic,
                    "pro_total": sc.get("pro",{}).get("total",0),
                    "con_total": sc.get("con",{}).get("total",0),
                    "winner": sc.get("winner","-"),
                    "transcript": transcript,
                    "feedback": st.session_state.user_feedback_text
                })
                st.session_state.debate_eval=True; st.rerun()
            else:
                st.subheader("토론 평가")
                score=st.session_state.get("score_json",{})
                if score:
                    st.write(f"**점수 요약** · 찬성: **{score.get('pro',{}).get('total','-')}점**, 반대: **{score.get('con',{}).get('total','-')}점**  → **승리: {score.get('winner','-')}**")
                st.markdown("**내 발언 기준 피드백**"); st.write(st.session_state.get("user_feedback_text",""))
                transcript=[]
                for m in st.session_state.debate_chat:
                    if m["role"]=="user": transcript.append(f"학생({st.session_state.user_side}): {m['content']}")
                    elif m["role"]=="assistant": transcript.append(f"챗봇({st.session_state.bot_side}): {m['content']}")
                data, mime, fname = build_debate_txt_bytes(title, st.session_state.debate_topic, st.session_state.user_side, transcript, score, st.session_state.get("user_feedback_text",""))
                st.download_button("🧾 토론 기록 TXT 저장", data=data, file_name=fname, mime=mime, key="debate_txt_dl")

# ───── PAGE 5 : 감상문 피드백 ─────
def page_feedback():
    st.header("✍️ 5) 독서 생각 성찰하기")
    if st.sidebar.button("피드백 초기화"): st.session_state.pop("essay",""); st.session_state.pop("ocr_file",""); st.rerun()
    if st.session_state.get("selected_book"):
        title=clean_html(st.session_state.selected_book["title"]); syn=st.session_state.synopsis
        st.markdown(f"**책:** {title}  &nbsp;&nbsp; <span class='badge'>난이도: {st.session_state.level}</span>", unsafe_allow_html=True)
    else: title="제목 없음"; syn=""

    up=st.file_uploader("손글씨 사진 업로드",type=["png","jpg","jpeg"])
    if up and st.session_state.get("ocr_file")!=up.name:
        st.session_state.essay=nv_ocr(up.read()); st.session_state.ocr_file=up.name; st.rerun()

    essay=st.text_area("감상문 입력 또는 OCR 결과", value=st.session_state.get("essay",""), key="essay", height=240)
    if st.button("🧭 피드백 받기"):
        if not essay.strip(): st.error("감상문을 입력하거나 업로드하세요"); return
        depth="간단히" if st.session_state.level=="쉬움" else ("충분히 자세히" if st.session_state.level=="기본" else "구체적 근거와 함께")
        fb_prompt=("너는 초등 글쓰기 코치야. 학생 감상문을 **선택한 책의 줄거리**와 비교하여 칭찬과 수정 제안을 해줘. 점수/일치도 말하지 마.\n"
                   "출력: 1) 내용 피드백 2) 표현·구성 피드백 3) 수정 예시("+depth+")\n\n"
                   "다음 항목을 고려해줘 1) 인상 깊은 부분이 잘나타났는가 2) 자신의 생각이나 느낌이 잘드러났는가 3) 줄거리가 잘 드러났는가 4) 맞춤법과 문법이 정확한가\n"
                   f"선택 책: {title}\n줄거리:\n{syn}\n\n학생 감상문:\n{essay}")
        fb=gpt([{"role":"user","content":fb_prompt}],level_params(st.session_state.level)['temp'],2300)
        st.subheader("피드백 결과"); st.write(fb)
        save_event("essay", {"title": title, "essay": essay, "feedback": fb, "level": st.session_state.level})

# ───── PAGE 6 : 포트폴리오 & 대시보드 ─────
def page_portfolio_dashboard():
    st.header("🎒 6) 나의 독서 앨범")
    st.caption("먼저 학년도/학교/학년/반/번호를 고르면, 그 아래에 기록을 정리해 보여줍니다. 번호가 0이면 학급 전체 집계입니다.")
    col1,col2,col3,col4,col5 = st.columns(5)
    year  = col1.number_input("학년도", min_value=2020, max_value=2100, value=int(st.session_state.get("year", datetime.datetime.now().year)), step=1)
    school= col2.text_input("학교", value=_norm_school(st.session_state.get("school","")))
    grade = col3.number_input("학년(0=전체)", min_value=0, max_value=6, value=int(st.session_state.get("grade",0)), step=1)
    klass = col4.number_input("반(0=전체)", min_value=0, max_value=20, value=int(st.session_state.get("klass",0)), step=1)
    number= col5.number_input("번호(0=전체)", min_value=0, max_value=50, value=0, step=1)

    # 현재 검색 키로 만들어지는 학생ID를 안내 (디버그·확인용)
    if year and school and grade and klass and number:
        st.caption(f"검색 학생ID: **{int(year)}-{_norm_school(school)}-{int(grade)}-{int(klass)}-{int(number)}**")

    df = db_dashboard(year=int(year), school=_norm_school(school), grade=int(grade), klass=int(klass), number=int(number))
    if df.empty:
        st.info("조건에 맞는 기록이 없습니다."); return

    quiz_scores=[d.get("score") for d in df[df["page"]=="quiz"]["payload"].tolist() if isinstance(d,dict) and "score" in d]
    pro_tot=[d.get("pro_total") for d in df[df["page"]=="debate"]["payload"].tolist() if "pro_total" in d]
    con_tot=[d.get("con_total") for d in df[df["page"]=="debate"]["payload"].tolist() if "con_total" in d]
    books=[d.get("title") for d in df[df["page"]=="book"]["payload"].tolist() if "title" in d]
    colm = st.columns(5)
    colm[0].metric("총 활동 건수", len(df))
    colm[1].metric("평균 퀴즈 점수", round(sum(quiz_scores)/len(quiz_scores),1) if quiz_scores else 0.0)
    colm[2].metric("평균(찬성) 토론점수", round(sum(pro_tot)/len(pro_tot),1) if pro_tot else 0.0)
    colm[3].metric("평균(반대) 토론점수", round(sum(con_tot)/len(con_tot),1) if con_tot else 0.0)
    top_book = Counter(books).most_common(1)[0][0] if books else "-"
    colm[4].metric("가장 많이 선택한 책", top_book)
    if number==0:
        st.subheader("📈 학급 활동 요약 (전체)")
        pie_df = df["page"].value_counts().rename_axis("활동").reset_index(name="건수")
        st.bar_chart(pie_df.set_index("활동"))
        if quiz_scores:
            st.markdown("**퀴즈 점수 분포**"); st.area_chart(pd.DataFrame({"score":quiz_scores})["score"])
        book_df = df[df["page"]=="book"].copy()
        if not book_df.empty:
            book_df["month"]=pd.to_datetime(book_df["ts"]).dt.to_period("M").astype(str)
            monthly_read = book_df.groupby("month").size().reset_index(name="reads")
            st.markdown("**월별 독서 수**"); st.bar_chart(monthly_read.set_index("month"))
        else:
            st.info("아직 책 선택(독서) 기록이 없어 '월별 독서 수' 그래프를 표시할 수 없습니다.")
        if books:
            top5=pd.DataFrame(Counter(books).most_common(5), columns=["책","건수"]).set_index("책")
            st.markdown("**가장 많이 선택한 책 Top5**"); st.bar_chart(top5)
        st.subheader("📜 최근 활동 로그 (일부)")
        st.dataframe(df[["ts","student_id","page"]].tail(50), use_container_width=True)
        return
    st.subheader("🙋 선택 학생 포트폴리오")
    sid=f"{int(year)}-{_norm_school(school)}-{int(grade)}-{int(klass)}-{int(number)}"
    st.caption(f"학생 ID: {sid}")
    sdf=df.copy()
    if sdf.empty:
        st.info("이 학생의 기록이 없습니다."); return
    qrows=[(r["ts"], r["payload"].get("score")) for _,r in sdf[sdf["page"]=="quiz"].iterrows() if "score" in r["payload"]]
    if qrows:
        qdf=pd.DataFrame(qrows, columns=["ts","score"]).set_index("ts")
        st.markdown("**퀴즈 점수 변화**"); st.line_chart(qdf)
    drows=list(sdf[sdf["page"]=="debate"]["payload"])
    if drows:
        last=drows[-1]
        colx, coly = st.columns([1,1])
        colx.metric("최근 토론(찬성) 점수", last.get("pro_total","-"))
        coly.metric("최근 토론(반대) 점수", last.get("con_total","-"))
        st.markdown("**최근 토론 주제**: " + str(last.get("topic","-")))
        st.markdown("**토론 로그**"); st.text("\n".join(last.get("transcript",[])))
        st.markdown("**토론 피드백**"); st.write(last.get("feedback",""))
    erows = sdf[sdf["page"] == "essay"].copy()
    if not erows.empty:
        erows["ts_dt"] = pd.to_datetime(erows["ts"], errors="coerce")
        erows = erows.sort_values("ts_dt")
        st.subheader("✍️ 독서감상문 피드백")
        opts, idxs = [], []
        for i, row in erows.iterrows():
            payload = row["payload"] if isinstance(row["payload"], dict) else {}
            title = payload.get("title", "-")
            when = row.get("ts_dt")
            label = f'{when.strftime("%Y-%m-%d %H:%M") if pd.notna(when) else row["ts"]} · {title}'
            opts.append(label); idxs.append(i)
        pick = st.selectbox("감상문 선택", options=range(len(opts)), format_func=lambda k: opts[k], index=len(opts)-1)
        chosen = erows.loc[idxs[pick], "payload"]
        if not isinstance(chosen, dict):
            try: chosen = json.loads(chosen)
            except Exception: chosen = {}
        e_title = chosen.get("title", "-")
        e_text  = chosen.get("essay", "").strip()
        e_fb    = chosen.get("feedback", "").strip()
        st.markdown(f"**책 제목:** {e_title}")
        with st.expander("📝 학생 감상문(원문) 보기", expanded=False):
            st.text(e_text or "(입력된 감상문이 없습니다.)")
        st.markdown("**피드백**"); st.write(e_fb or "(피드백 내용이 없습니다.)")
        if e_text or e_fb:
            txt = f"독서감상문 기록\n\n[책] {e_title}\n\n[학생 감상문]\n{e_text}\n\n[피드백]\n{e_fb}\n"
            st.download_button("📥 감상문+피드백 TXT 저장", data=txt.encode("utf-8"),
                               file_name="essay_feedback.txt", mime="text/plain", key="essay_txt_dl")

# ───── MAIN ─────
def main():
    st.set_page_config("북클라이밍","📚",layout="wide")
    font_choice = st.session_state.get("ui_font_size_choice","보통")
    st.markdown(theme_css(FONT_SIZES.get(font_choice,"16px")), unsafe_allow_html=True)
    st.title("북클라이밍: 자기주도적 독서 습관 기르기")

    if "current_page" not in st.session_state: st.session_state.current_page="책 검색"
    if "level" not in st.session_state: st.session_state.level="기본"

    with st.sidebar:
        st.link_button("ℹ️ 프로그램 사용법", "https://www.canva.com")
        student_panel()
        st.markdown("### 메뉴")
        menu_labels={
            "책 검색":"📘 책 찾기 & 표지 이야기",
            "단어 알아보기":"🧩 낱말 탐정",
            "독서 퀴즈":"📝 이야기 퀴즈",
            "독서 토론":"🗣️ 독서 생각 나누기",
            "독서 감상문 피드백":"✍️ 독서 생각 성찰하기",
            "포트폴리오/대시보드":"🎒 나의 독서 앨범"
        }
        st.markdown('<div class="sidebar-radio">', unsafe_allow_html=True)
        sel=st.radio("", list(menu_labels.keys()),
                     format_func=lambda k: menu_labels[k],
                     index=list(menu_labels).index(st.session_state.current_page),
                     label_visibility="collapsed")
        st.markdown('</div>', unsafe_allow_html=True)
        st.session_state.current_page=sel

        st.markdown("---")
        try:
            st.link_button("🌐 독서감상문 공유", "http://wwww.example.com")
        except Exception:
            st.markdown('<a class="linklike-btn" href="http://wwww.example.com" target="_blank">🌐 독서감상문 공유</a>', unsafe_allow_html=True)

        if st.button("처음으로"): st.session_state.clear(); st.rerun()

    pages={
        "책 검색":page_book,
        "단어 알아보기":page_vocab,
        "독서 퀴즈":page_quiz,
        "독서 토론":page_discussion,
        "독서 감상문 피드백":page_feedback,
        "포트폴리오/대시보드":page_portfolio_dashboard
    }
    pages[st.session_state.current_page]()

if __name__=="__main__":
    main()



