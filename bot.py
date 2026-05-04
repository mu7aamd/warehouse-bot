#!/usr/bin/env python3
"""
🏭 نظام إدارة المستودعات — بوت تلغرام
"""
import logging, sqlite3, os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler, filters, ContextTypes)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# ══ CONFIG ═══════════════════════════════════════════════
BOT_TOKEN = "8688642312:AAG6TtSlPeu8dKYfJM3ysseZI6k93nLDjMk"
GROUP_ID  = int("-5160076602")

WORKERS    = ['ابو صلاح','قوقل','روبن','رضاي','سليم','رفعت','صابر','عبدالرحمن']
WAREHOUSES = ['مستودع 5','مستودع 16','مستودع 20','مستودع 22']
DB_FILE    = 'warehouse.db'

# ══ STATES ═══════════════════════════════════════════════
(MAIN,
 IN_WH,IN_CODE,IN_NAME,IN_QTY,IN_WORKER,
 ORD_SRC,ORD_CODE,ORD_NAME,ORD_QTY,ORD_PRI,ORD_NOTES,
 MFG_TYPE,MFG_CODE,MFG_QTY,MFG_PRI,MFG_DL,MFG_WORKERS,MFG_DETAILS,MFG_DEL,
 VST_TYPE,VST_QTY,VST_LOGO,VST_DL,VST_WORKERS,
 RDY_CODE,RDY_NAME,RDY_QTY,RDY_WH,RDY_DEST,RDY_WHO,RDY_WORKER,
 DRV_DRIVER,DRV_CODE,DRV_QTY,DRV_ADDR,DRV_PHONE,
 SHP_CO,SHP_CODE,SHP_QTY,SHP_CITY,SHP_WORKER,
 TRK_CODE,TRK_QTY,TRK_DEST,TRK_PLATE,TRK_PHONE,TRK_WORKERS,
 PC_DRIVER,PC_TYPE,PC_QTY,PC_PRINT,
 CD_DRIVER,CD_CODE,CD_QTY,CD_CLIENT,
 CS_CO,CS_CODE,CS_QTY,CS_TRACK,
 CT_CODE,CT_QTY,CT_PLATE,CT_DNAME,CT_STATUS,
) = range(65)

TYPE_LABELS = {
 'incoming':'📦 بضاعة واردة','order':'🛒 طلبية','manufacture':'🔧 تجهيز',
 'vest':'👕 سترات','ready':'✅ جاهزة','driver_out':'🚗 توصيل',
 'shipping':'📦 شحن','truck':'🚛 دينة','print_confirm':'🖨️ مطبعة',
 'confirm_driver':'✅ تأكيد سائق','confirm_shipping':'✅ تأكيد شحن','confirm_truck':'✅ تأكيد دينة',
}

# ══ DATABASE ══════════════════════════════════════════════
def init_db():
    c=sqlite3.connect(DB_FILE)
    c.execute('CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT,type TEXT,message TEXT,actor TEXT,created_at TEXT)')
    c.commit(); c.close()

def log_event(t,msg,actor):
    c=sqlite3.connect(DB_FILE)
    c.execute('INSERT INTO logs(type,message,actor,created_at) VALUES(?,?,?,?)',(t,msg,actor,datetime.now().strftime('%Y-%m-%d %H:%M')))
    c.commit(); c.close()

def get_today():
    today=datetime.now().strftime('%Y-%m-%d')
    c=sqlite3.connect(DB_FILE)
    rows=c.execute("SELECT type,actor,created_at FROM logs WHERE created_at LIKE ? ORDER BY created_at DESC",(today+'%',)).fetchall()
    c.close(); return rows

# ══ HELPERS ═══════════════════════════════════════════════
def now(): return datetime.now().strftime('%H:%M')
def opt(d,k,lbl='',empty=''):
    val=(d.get(k) or '').strip()
    if not val or val=='-': return empty
    return f"\n{lbl}{val}" if lbl else val
def picon(p): return {'عادي':'🟢','عاجل':'🟡','جداً عاجل':'🔴'}.get(p,'🟢')

async def grp(ctx,msg):
    try: await ctx.bot.send_message(chat_id=GROUP_ID,text=msg,parse_mode='Markdown')
    except Exception as e: logging.error(f"Group: {e}")

# ══ KEYBOARDS ═════════════════════════════════════════════
def KB():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 بضاعة واردة",callback_data="flow_incoming"),
         InlineKeyboardButton("🛒 طلبية جديدة",callback_data="flow_order")],
        [InlineKeyboardButton("🔧 أمر تجهيز",callback_data="flow_mfg"),
         InlineKeyboardButton("👕 سترات مطبعة",callback_data="flow_vest")],
        [InlineKeyboardButton("✅ طلبية جاهزة عند الباب",callback_data="flow_ready")],
        [InlineKeyboardButton("── التوصيل والشحن ──",callback_data="noop")],
        [InlineKeyboardButton("🚗 توصيل سائقنا",callback_data="flow_driver"),
         InlineKeyboardButton("📦 شركة شحن",callback_data="flow_shipping")],
        [InlineKeyboardButton("🚛 دينة مستأجرة",callback_data="flow_truck"),
         InlineKeyboardButton("🖨️ استلام مطبعة",callback_data="flow_printconfirm")],
        [InlineKeyboardButton("── تأكيدات التسليم ──",callback_data="noop")],
        [InlineKeyboardButton("✅ تأكيد سائقنا",callback_data="flow_cdriver"),
         InlineKeyboardButton("✅ تأكيد شحن",callback_data="flow_cshipping")],
        [InlineKeyboardButton("✅ تأكيد دينة",callback_data="flow_ctruck")],
        [InlineKeyboardButton("📊 تقرير اليوم",callback_data="flow_report")],
    ])

def KW(selected=None):
    s=selected or []
    rows=[[InlineKeyboardButton(("✅ " if w in s else "⬜ ")+w,callback_data=f'wr_{w}')] for w in WORKERS]
    rows.append([InlineKeyboardButton("➡️ تأكيد الاختيار",callback_data='wr_done')])
    rows.append([InlineKeyboardButton("❌ إلغاء",callback_data='cancel')])
    return InlineKeyboardMarkup(rows)

def KS():
    rows=[[InlineKeyboardButton(w,callback_data=f'sw_{w}')] for w in WORKERS]
    rows.append([InlineKeyboardButton("❌ إلغاء",callback_data='cancel')])
    return InlineKeyboardMarkup(rows)

def KWH():
    rows=[[InlineKeyboardButton(w,callback_data=f'wh_{w}')] for w in WAREHOUSES]
    rows.append([InlineKeyboardButton("❌ إلغاء",callback_data='cancel')])
    return InlineKeyboardMarkup(rows)

def KPRI():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 عادي",callback_data='pri_عادي'),
        InlineKeyboardButton("🟡 عاجل",callback_data='pri_عاجل'),
        InlineKeyboardButton("🔴 جداً عاجل",callback_data='pri_جداً عاجل'),
    ],[InlineKeyboardButton("❌ إلغاء",callback_data='cancel')]])

def KLIST(items,pfx):
    rows=[[InlineKeyboardButton(i,callback_data=f'{pfx}{i}')] for i in items]
    rows.append([InlineKeyboardButton("❌ إلغاء",callback_data='cancel')])
    return InlineKeyboardMarkup(rows)

def KC(): return InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء",callback_data='cancel')]])

# ══ CORE ══════════════════════════════════════════════════
async def start(u,c):
    c.user_data.clear()
    await u.effective_message.reply_text("🏭 *نظام إدارة المستودعات*\n_الدار البيضاء — معرض الظهران_\n\nاختر العملية:",reply_markup=KB(),parse_mode='Markdown')
    return MAIN

async def cancel(u,c):
    c.user_data.clear()
    q=u.callback_query
    if q: await q.answer()
    await u.effective_message.reply_text("↩️ تم الإلغاء. اختر عملية:",reply_markup=KB())
    return MAIN

async def noop(u,c): await u.callback_query.answer(); return MAIN

async def finish(u,c,msg,etype,actor,warn=""):
    await grp(c,msg); log_event(etype,msg,actor)
    reply="✅ *تم الإرسال للقروب!*"+(f"\n\n⚠️ *{warn}*" if warn else "")
    await u.effective_message.reply_text(reply,reply_markup=KB(),parse_mode='Markdown')
    c.user_data.clear(); return MAIN

# ══ F1: بضاعة واردة ════════════════════════════════════════
async def f_incoming(u,c):
    q=u.callback_query; await q.answer()
    await q.message.reply_text("🏭 *المستودع:*",reply_markup=KWH(),parse_mode='Markdown'); return IN_WH

async def in_wh(u,c):
    q=u.callback_query; await q.answer(); c.user_data['wh']=q.data[3:]
    await q.message.reply_text("📋 *كود المنتج:*\nمثال: 1141",reply_markup=KC(),parse_mode='Markdown'); return IN_CODE

async def in_code(u,c):
    c.user_data['code']=u.message.text
    await u.message.reply_text("📝 اسم المنتج (أو - للتخطي):",reply_markup=KC()); return IN_NAME

async def in_name(u,c):
    c.user_data['name']=u.message.text
    await u.message.reply_text("📊 الكمية:",reply_markup=KC()); return IN_QTY

async def in_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return IN_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("👤 *العامل:*",reply_markup=KS(),parse_mode='Markdown'); return IN_WORKER

async def in_worker(u,c):
    q=u.callback_query; await q.answer(); d=c.user_data; d['worker']=q.data[3:]
    msg=(f"📦 *بضاعة واردة*\n─────────────────\n"
         f"🏭 المستودع: {d['wh']}\n📋 الكود: {d['code']}{opt(d,'name','📝 المنتج: ')}\n"
         f"📊 الكمية: {d['qty']} قطعة\n👤 العامل: {d['worker']}\n🕐 الوقت: {now()}\n"
         f"─────────────────\n✅ تم الاستلام والتخزين")
    return await finish(u,c,msg,'incoming',d['worker'])

# ══ F2: طلبية جديدة ════════════════════════════════════════
SOURCES=['عميل خارجي','المدير','معرض الظهران']

async def f_order(u,c):
    q=u.callback_query; await q.answer()
    await q.message.reply_text("📌 *مصدر الطلب:*",reply_markup=KLIST(SOURCES,'src_'),parse_mode='Markdown'); return ORD_SRC

async def o_src(u,c):
    q=u.callback_query; await q.answer(); c.user_data['src']=q.data[4:]
    await q.message.reply_text("📋 كود المنتج:",reply_markup=KC()); return ORD_CODE

async def o_code(u,c):
    c.user_data['code']=u.message.text
    await u.message.reply_text("📝 اسم المنتج (أو -):",reply_markup=KC()); return ORD_NAME

async def o_name(u,c):
    c.user_data['name']=u.message.text
    await u.message.reply_text("📊 الكمية:",reply_markup=KC()); return ORD_QTY

async def o_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return ORD_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("⚡ الأولوية:",reply_markup=KPRI()); return ORD_PRI

async def o_pri(u,c):
    q=u.callback_query; await q.answer(); c.user_data['pri']=q.data[4:]
    await q.message.reply_text("💬 ملاحظات (أو -):",reply_markup=KC()); return ORD_NOTES

async def o_notes(u,c):
    d=c.user_data; d['notes']=u.message.text; pri=d.get('pri','عادي')
    msg=(f"🛒 *طلبية جديدة*\n─────────────────\n"
         f"📌 المصدر: {d['src']}\n📋 الكود: {d['code']}{opt(d,'name','📝 المنتج: ')}\n"
         f"📊 الكمية: {d['qty']}\n{picon(pri)} الأولوية: {pri}\n"
         f"🕐 الوقت: {now()}{opt(d,'notes','💬 ملاحظات: ')}\n"
         f"─────────────────\n⏳ بانتظار التجهيز والتنفيذ")
    return await finish(u,c,msg,'order',u.effective_user.first_name or '')

# ══ F3: أمر تجهيز ══════════════════════════════════════════
MFGTYPES=['تجهيز سيارة دورية','تصنيع لوحات تحذيرية','تجهيز أسهم تحذيرية','تجهيز مجموعة سلامة','تركيب أضواء طوارئ','أخرى']
DELOPTS=['سائق من عمالنا','شركة شحن','دينة مستأجرة','لم يحدد بعد']

async def f_mfg(u,c):
    q=u.callback_query; await q.answer(); c.user_data['sel_workers']=[]
    await q.message.reply_text("🔧 *نوع العمل:*",reply_markup=KLIST(MFGTYPES,'mt_'),parse_mode='Markdown'); return MFG_TYPE

async def m_type(u,c):
    q=u.callback_query; await q.answer(); c.user_data['mtype']=q.data[3:]
    await q.message.reply_text("📋 كود المنتج (أو -):",reply_markup=KC()); return MFG_CODE

async def m_code(u,c):
    c.user_data['code']=u.message.text
    await u.message.reply_text("📊 الكمية:",reply_markup=KC()); return MFG_QTY

async def m_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return MFG_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("⚡ الأولوية:",reply_markup=KPRI()); return MFG_PRI

async def m_pri(u,c):
    q=u.callback_query; await q.answer(); c.user_data['pri']=q.data[4:]
    await q.message.reply_text("⏰ موعد التسليم (مثال: اليوم 3م) أو -:",reply_markup=KC()); return MFG_DL

async def m_dl(u,c):
    c.user_data['dl']=u.message.text
    await u.message.reply_text("👷 *اختر العمال:*\n(اضغط الاسم للتحديد ثم تأكيد)",reply_markup=KW([]),parse_mode='Markdown'); return MFG_WORKERS

async def m_workers(u,c):
    q=u.callback_query; await q.answer()
    if q.data=='wr_done':
        await q.message.reply_text("📌 تفاصيل المهمة (أو -):",reply_markup=KC()); return MFG_DETAILS
    w=q.data[3:]; s=c.user_data.get('sel_workers',[])
    if w in s: s.remove(w)
    else: s.append(w)
    c.user_data['sel_workers']=s
    await q.message.edit_reply_markup(reply_markup=KW(s)); return MFG_WORKERS

async def m_details(u,c):
    c.user_data['details']=u.message.text
    await u.message.reply_text("🚚 طريقة التوصيل بعد التجهيز:",reply_markup=KLIST(DELOPTS,'del_')); return MFG_DEL

async def m_del(u,c):
    q=u.callback_query; await q.answer(); d=c.user_data; d['delivery']=q.data[4:]
    s=d.get('sel_workers',[]); wstr=' - '.join(s) if s else 'الفريق كله'
    pri=d.get('pri','عادي')
    det=opt(d,'details','\n📌 تفاصيل:\n')
    msg=(f"🔧 *أمر تجهيز / تصنيع*\n─────────────────\n"
         f"📋 نوع العمل: {d['mtype']}{opt(d,'code','🔢 الكود: ')}\n"
         f"📊 الكمية: {d['qty']}\n{picon(pri)} الأولوية: {pri}{opt(d,'dl','⏰ التسليم: ')}\n"
         f"👷 المكلفون: {wstr}\n🚚 التوصيل: {d['delivery']}\n🕐 الوقت: {now()}{det}\n"
         f"─────────────────\n⏳ العمال يردون بـ \"تم ✅\" عند الانتهاء")
    return await finish(u,c,msg,'manufacture',u.effective_user.first_name or '')

# ══ F4: سترات ══════════════════════════════════════════════
async def f_vest(u,c):
    q=u.callback_query; await q.answer(); c.user_data['sel_workers']=[]
    await q.message.reply_text("👕 نوع السترات / البدلات:",reply_markup=KC()); return VST_TYPE

async def v_type(u,c):
    c.user_data['vtype']=u.message.text
    await u.message.reply_text("📊 الكمية:",reply_markup=KC()); return VST_QTY

async def v_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return VST_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("🖨️ تفاصيل الشعار / الطباعة:",reply_markup=KC()); return VST_LOGO

async def v_logo(u,c):
    c.user_data['logo']=u.message.text
    await u.message.reply_text("⏰ موعد الإرسال للمطبعة (أو -):",reply_markup=KC()); return VST_DL

async def v_dl(u,c):
    c.user_data['dl']=u.message.text
    await u.message.reply_text("👷 *اختر العمال:*",reply_markup=KW([]),parse_mode='Markdown'); return VST_WORKERS

async def v_workers(u,c):
    q=u.callback_query; await q.answer()
    if q.data=='wr_done':
        d=c.user_data; s=d.get('sel_workers',[]); wstr=' - '.join(s) if s else 'الفريق كله'
        msg=(f"👕 *طلبية سترات للمطبعة*\n─────────────────\n"
             f"📝 النوع: {d['vtype']}\n📊 الكمية: {d['qty']}{opt(d,'logo','🖨️ الطباعة: ')}\n"
             f"👷 التجهيز: {wstr}{opt(d,'dl','⏰ موعد الإرسال: ')}\n🕐 الوقت: {now()}\n"
             f"─────────────────\n⏳ توضع عند الباب جاهزة للاستلام")
        return await finish(u,c,msg,'vest',u.effective_user.first_name or '')
    w=q.data[3:]; s=c.user_data.get('sel_workers',[])
    if w in s: s.remove(w)
    else: s.append(w)
    c.user_data['sel_workers']=s
    await q.message.edit_reply_markup(reply_markup=KW(s)); return VST_WORKERS

# ══ F5: طلبية جاهزة ════════════════════════════════════════
DESTLIST=['معرض الظهران','عميل داخل الرياض','شركة شحن خارج الرياض','مطبعة','دينة مستأجرة']

async def f_ready(u,c):
    q=u.callback_query; await q.answer()
    await q.message.reply_text("📋 كود المنتج (أو -):",reply_markup=KC()); return RDY_CODE

async def r_code(u,c):
    c.user_data['code']=u.message.text
    await u.message.reply_text("📝 وصف / اسم الطلبية:",reply_markup=KC()); return RDY_NAME

async def r_name(u,c):
    c.user_data['rname']=u.message.text
    await u.message.reply_text("📊 الكمية:",reply_markup=KC()); return RDY_QTY

async def r_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return RDY_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("🏭 المستودع:",reply_markup=KWH()); return RDY_WH

async def r_wh(u,c):
    q=u.callback_query; await q.answer(); c.user_data['wh']=q.data[3:]
    await q.message.reply_text("🎯 الوجهة:",reply_markup=KLIST(DESTLIST,'dst_')); return RDY_DEST

async def r_dest(u,c):
    q=u.callback_query; await q.answer(); c.user_data['dest']=q.data[4:]
    await q.message.reply_text("🚚 من سيأخذها؟ (اكتب الاسم):",reply_markup=KC()); return RDY_WHO

async def r_who(u,c):
    c.user_data['who']=u.message.text
    await u.message.reply_text("👤 من جهّزها؟",reply_markup=KS()); return RDY_WORKER

async def r_worker(u,c):
    q=u.callback_query; await q.answer(); d=c.user_data; d['prep']=q.data[3:]
    msg=(f"✅ *طلبية جاهزة عند الباب*\n─────────────────\n"
         f"{opt(d,'code','📋 الكود: ')}\n📝 الطلبية: {d['rname']}\n"
         f"📊 الكمية: {d['qty']}\n🏭 في: {d['wh']}\n🎯 الوجهة: {d['dest']}\n"
         f"🚚 سيأخذها: {d['who']}\n👤 جهّزها: {d['prep']}\n🕐 الوقت: {now()}\n"
         f"─────────────────\n📣 جميع العمال على علم\nمن سيستلمها يؤكد في القروب ✅")
    return await finish(u,c,msg,'ready',d['prep'])

# ══ F6: توصيل سائقنا ════════════════════════════════════════
async def f_driver(u,c):
    q=u.callback_query; await q.answer()
    await q.message.reply_text("👤 *اختر السائق:*",reply_markup=KS(),parse_mode='Markdown'); return DRV_DRIVER

async def d_driver(u,c):
    q=u.callback_query; await q.answer(); c.user_data['driver']=q.data[3:]
    await q.message.reply_text("📋 كود / وصف الطلبية:",reply_markup=KC()); return DRV_CODE

async def d_code(u,c):
    c.user_data['code']=u.message.text
    await u.message.reply_text("📊 الكمية:",reply_markup=KC()); return DRV_QTY

async def d_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return DRV_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("📍 عنوان العميل (أو -):",reply_markup=KC()); return DRV_ADDR

async def d_addr(u,c):
    c.user_data['addr']=u.message.text
    await u.message.reply_text("📞 هاتف العميل (أو -):",reply_markup=KC()); return DRV_PHONE

async def d_phone(u,c):
    d=c.user_data; d['phone']=u.message.text
    msg=(f"🚗 *خروج للتوصيل — سائقنا*\n─────────────────\n"
         f"👤 السائق: {d['driver']}\n📋 الطلبية: {d['code']}\n"
         f"📊 الكمية: {d['qty']}{opt(d,'addr','📍 العنوان: ')}{opt(d,'phone','📞 العميل: ')}\n"
         f"🕐 الوقت: {now()}\n─────────────────\n⏳ بعد التسليم يرسل تأكيد + 📸 سند الاستلام")
    return await finish(u,c,msg,'driver_out',d['driver'])

# ══ F7: شركة شحن ════════════════════════════════════════════
async def f_shipping(u,c):
    q=u.callback_query; await q.answer()
    await q.message.reply_text("🏢 اسم شركة الشحن:",reply_markup=KC()); return SHP_CO

async def s_co(u,c):
    c.user_data['co']=u.message.text
    await u.message.reply_text("📋 كود / وصف الطلبية:",reply_markup=KC()); return SHP_CODE

async def s_code(u,c):
    c.user_data['code']=u.message.text
    await u.message.reply_text("📊 الكمية:",reply_markup=KC()); return SHP_QTY

async def s_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return SHP_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("🌆 المدينة الوجهة:",reply_markup=KC()); return SHP_CITY

async def s_city(u,c):
    c.user_data['city']=u.message.text
    await u.message.reply_text("👤 من سيسلّمها للشحن؟",reply_markup=KS()); return SHP_WORKER

async def s_worker(u,c):
    q=u.callback_query; await q.answer(); d=c.user_data; d['worker']=q.data[3:]
    msg=(f"📦 *تسليم شركة شحن*\n─────────────────\n"
         f"🏢 الشركة: {d['co']}\n📋 الطلبية: {d['code']}\n"
         f"📊 الكمية: {d['qty']}\n🌆 الوجهة: {d['city']}\n"
         f"👤 سلّمها: {d['worker']}\n🕐 الوقت: {now()}\n"
         f"─────────────────\n⏳ يرسل تأكيد + 📸 إيصال الشحن")
    return await finish(u,c,msg,'shipping',d['worker'])

# ══ F8: دينة مستأجرة ════════════════════════════════════════
async def f_truck(u,c):
    q=u.callback_query; await q.answer(); c.user_data['sel_workers']=[]
    await q.message.reply_text("📋 كود / وصف الطلبية:",reply_markup=KC()); return TRK_CODE

async def t_code(u,c):
    c.user_data['code']=u.message.text
    await u.message.reply_text("📊 الكمية:",reply_markup=KC()); return TRK_QTY

async def t_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return TRK_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("📍 وجهة التسليم:",reply_markup=KC()); return TRK_DEST

async def t_dest(u,c):
    c.user_data['dest']=u.message.text
    await u.message.reply_text("🚛 رقم لوحة الدينة:",reply_markup=KC()); return TRK_PLATE

async def t_plate(u,c):
    c.user_data['plate']=u.message.text
    await u.message.reply_text("📞 هاتف سائق الدينة (أو -):",reply_markup=KC()); return TRK_PHONE

async def t_phone(u,c):
    c.user_data['dphone']=u.message.text
    await u.message.reply_text("👷 *اختر فريق التحميل:*",reply_markup=KW([]),parse_mode='Markdown'); return TRK_WORKERS

async def t_workers(u,c):
    q=u.callback_query; await q.answer()
    if q.data=='wr_done':
        d=c.user_data; s=d.get('sel_workers',[]); wstr=' - '.join(s) if s else 'الفريق كله'
        msg=(f"🚛 *دينة مستأجرة — تحميل*\n─────────────────\n"
             f"📋 الطلبية: {d['code']}\n📊 الكمية: {d['qty']}\n"
             f"📍 الوجهة: {d['dest']}\n🚛 لوحة الدينة: {d['plate']}{opt(d,'dphone','📞 سائق الدينة: ')}\n"
             f"👷 فريق التحميل: {wstr}\n🕐 الوقت: {now()}\n"
             f"─────────────────\n⏳ بعد التحميل يرسل تأكيد + 📸 سند + هوية السائق")
        return await finish(u,c,msg,'truck',u.effective_user.first_name or '')
    w=q.data[3:]; s=c.user_data.get('sel_workers',[])
    if w in s: s.remove(w)
    else: s.append(w)
    c.user_data['sel_workers']=s
    await q.message.edit_reply_markup(reply_markup=KW(s)); return TRK_WORKERS

# ══ F9: استلام المطبعة ══════════════════════════════════════
async def f_printconfirm(u,c):
    q=u.callback_query; await q.answer()
    await q.message.reply_text("👤 *السائق المستلِم:*",reply_markup=KS(),parse_mode='Markdown'); return PC_DRIVER

async def p_driver(u,c):
    q=u.callback_query; await q.answer(); c.user_data['driver']=q.data[3:]
    await q.message.reply_text("📝 نوع السترات / البدلات:",reply_markup=KC()); return PC_TYPE

async def p_type(u,c):
    c.user_data['ptype']=u.message.text
    await u.message.reply_text("📊 الكمية المستلمة:",reply_markup=KC()); return PC_QTY

async def p_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return PC_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("🏪 اسم المطبعة (أو -):",reply_markup=KC()); return PC_PRINT

async def p_print(u,c):
    d=c.user_data; d['printname']=u.message.text
    msg=(f"🖨️ *استلام سترات للمطبعة*\n─────────────────\n"
         f"👤 السائق: {d['driver']}\n📝 النوع: {d['ptype']}\n"
         f"📊 الكمية: {d['qty']}{opt(d,'printname','🏪 المطبعة: ')}\n🕐 الوقت: {now()}\n"
         f"─────────────────\n✅ السائق استلم وتوجه للمطبعة")
    return await finish(u,c,msg,'print_confirm',d['driver'])

# ══ F10: تأكيد سائقنا ══════════════════════════════════════
async def f_cdriver(u,c):
    q=u.callback_query; await q.answer()
    await q.message.reply_text("📸 *تذكير:* أرفق سند الاستلام في القروب بعد الإرسال!\n\n👤 السائق:",reply_markup=KS(),parse_mode='Markdown'); return CD_DRIVER

async def cd_driver(u,c):
    q=u.callback_query; await q.answer(); c.user_data['driver']=q.data[3:]
    await q.message.reply_text("📋 كود / وصف الطلبية:",reply_markup=KC()); return CD_CODE

async def cd_code(u,c):
    c.user_data['code']=u.message.text
    await u.message.reply_text("📊 الكمية المُسلَّمة:",reply_markup=KC()); return CD_QTY

async def cd_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return CD_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("👤 اسم المستلِم (العميل):",reply_markup=KC()); return CD_CLIENT

async def cd_client(u,c):
    d=c.user_data; d['client']=u.message.text
    msg=(f"✅ *تأكيد التسليم — سائقنا*\n─────────────────\n"
         f"👤 السائق: {d['driver']}\n📋 الطلبية: {d['code']}\n"
         f"📊 الكمية: {d['qty']}\n👤 استلمها: {d['client']}\n🕐 الوقت: {now()}\n"
         f"─────────────────\n📸 *صورة سند الاستلام مرفقة*\n✅ تم التسليم بنجاح")
    return await finish(u,c,msg,'confirm_driver',d['driver'],"أرسل صورة سند الاستلام في القروب الآن 📸")

# ══ F11: تأكيد شحن ══════════════════════════════════════════
async def f_cshipping(u,c):
    q=u.callback_query; await q.answer()
    await q.message.reply_text("📸 *تذكير:* أرفق إيصال الشحن في القروب!\n\n🏢 شركة الشحن:",reply_markup=KC(),parse_mode='Markdown'); return CS_CO

async def cs_co(u,c):
    c.user_data['co']=u.message.text
    await u.message.reply_text("📋 كود / وصف الطلبية:",reply_markup=KC()); return CS_CODE

async def cs_code(u,c):
    c.user_data['code']=u.message.text
    await u.message.reply_text("📊 الكمية:",reply_markup=KC()); return CS_QTY

async def cs_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return CS_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("🏷️ رقم التتبع / البوليصة (أو -):",reply_markup=KC()); return CS_TRACK

async def cs_track(u,c):
    d=c.user_data; d['track']=u.message.text
    msg=(f"✅ *تأكيد الشحن*\n─────────────────\n"
         f"🏢 شركة الشحن: {d['co']}\n📋 الطلبية: {d['code']}\n"
         f"📊 الكمية: {d['qty']}{opt(d,'track','🏷️ رقم التتبع: ')}\n🕐 الوقت: {now()}\n"
         f"─────────────────\n📸 *إيصال الشحن مرفق*\n✅ تم تسليم الشحنة")
    return await finish(u,c,msg,'confirm_shipping',u.effective_user.first_name or '',"أرسل صورة الإيصال في القروب الآن 📸")

# ══ F12: تأكيد دينة ═════════════════════════════════════════
async def f_ctruck(u,c):
    q=u.callback_query; await q.answer()
    await q.message.reply_text("📸 *تذكير:* أرفق سند الاستلام + هوية السائق!\n\n📋 كود / وصف الطلبية:",reply_markup=KC(),parse_mode='Markdown'); return CT_CODE

async def ct_code(u,c):
    c.user_data['code']=u.message.text
    await u.message.reply_text("📊 الكمية المحمّلة:",reply_markup=KC()); return CT_QTY

async def ct_qty(u,c):
    if not u.message.text.strip().isdigit(): await u.message.reply_text("⚠️ أرسل رقماً"); return CT_QTY
    c.user_data['qty']=u.message.text.strip()
    await u.message.reply_text("🚛 رقم لوحة الدينة:",reply_markup=KC()); return CT_PLATE

async def ct_plate(u,c):
    c.user_data['plate']=u.message.text
    await u.message.reply_text("👤 اسم سائق الدينة:",reply_markup=KC()); return CT_DNAME

async def ct_dname(u,c):
    c.user_data['dname']=u.message.text
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ مكتمل",callback_data='cts_ok'),InlineKeyboardButton("⚠️ ناقص",callback_data='cts_warn')]])
    await u.message.reply_text("✅ حالة التحميل:",reply_markup=kb); return CT_STATUS

async def ct_status(u,c):
    q=u.callback_query; await q.answer(); d=c.user_data
    st="✅ مكتمل حسب الطلب" if q.data=='cts_ok' else "⚠️ ناقص — يرجى المراجعة"
    msg=(f"✅ *تأكيد التحميل — دينة مستأجرة*\n─────────────────\n"
         f"📋 الطلبية: {d['code']}\n📊 الكمية المحملة: {d['qty']}\n"
         f"🚛 لوحة الدينة: {d['plate']}\n👤 سائق الدينة: {d['dname']}\n"
         f"حالة التحميل: {st}\n🕐 الوقت: {now()}\n"
         f"─────────────────\n📸 *سند الاستلام + هوية السائق مرفقان*\n✅ تم التحميل والإقلاع")
    return await finish(u,c,msg,'confirm_truck',u.effective_user.first_name or '',"أرسل سند الاستلام وهوية السائق في القروب الآن 📸")

# ══ REPORT ════════════════════════════════════════════════
async def f_report(u,c):
    q=u.callback_query; await q.answer()
    logs=get_today()
    if not logs:
        await q.message.reply_text("📊 لا توجد عمليات اليوم بعد.",reply_markup=KB()); return MAIN
    cnt={}
    for r in logs: cnt[r[0]]=cnt.get(r[0],0)+1
    lines=[f"📊 *تقرير اليوم — {datetime.now().strftime('%Y-%m-%d')}*\n─────────────────"]
    for t,n in cnt.items(): lines.append(f"{TYPE_LABELS.get(t,t)}: {n}")
    lines+=["─────────────────",f"📋 الإجمالي: *{len(logs)}*"]
    await q.message.reply_text('\n'.join(lines),parse_mode='Markdown',reply_markup=KB()); return MAIN

async def cmd_report(u:Update,c:ContextTypes.DEFAULT_TYPE):
    logs=get_today()
    if not logs: await u.message.reply_text("📊 لا توجد عمليات اليوم."); return
    cnt={}
    for r in logs: cnt[r[0]]=cnt.get(r[0],0)+1
    lines=["📊 *تقرير اليوم*\n─────────────────"]
    for t,n in cnt.items(): lines.append(f"{TYPE_LABELS.get(t,t)}: {n}")
    lines+=["─────────────────",f"الإجمالي: *{len(logs)}*"]
    await u.message.reply_text('\n'.join(lines),parse_mode='Markdown')

# ══ MAIN ══════════════════════════════════════════════════
def main():
    init_db()
    app=Application.builder().token(BOT_TOKEN).build()
    CB=CallbackQueryHandler; cc=CB(cancel,pattern='^cancel$')

    conv=ConversationHandler(
        entry_points=[CommandHandler('start',start),CommandHandler('menu',start)],
        states={
            MAIN:[CB(f_incoming,'flow_incoming'),CB(f_order,'flow_order'),CB(f_mfg,'flow_mfg'),
                  CB(f_vest,'flow_vest'),CB(f_ready,'flow_ready'),CB(f_driver,'flow_driver'),
                  CB(f_shipping,'flow_shipping'),CB(f_truck,'flow_truck'),CB(f_printconfirm,'flow_printconfirm'),
                  CB(f_cdriver,'flow_cdriver'),CB(f_cshipping,'flow_cshipping'),CB(f_ctruck,'flow_ctruck'),
                  CB(f_report,'flow_report'),CB(noop,'noop')],
            IN_WH:[CB(in_wh,'^wh_'),cc], IN_CODE:[MessageHandler(filters.TEXT&~filters.COMMAND,in_code),cc],
            IN_NAME:[MessageHandler(filters.TEXT&~filters.COMMAND,in_name),cc],
            IN_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,in_qty),cc],
            IN_WORKER:[CB(in_worker,'^sw_'),cc],
            ORD_SRC:[CB(o_src,'^src_'),cc], ORD_CODE:[MessageHandler(filters.TEXT&~filters.COMMAND,o_code),cc],
            ORD_NAME:[MessageHandler(filters.TEXT&~filters.COMMAND,o_name),cc],
            ORD_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,o_qty),cc],
            ORD_PRI:[CB(o_pri,'^pri_'),cc], ORD_NOTES:[MessageHandler(filters.TEXT&~filters.COMMAND,o_notes),cc],
            MFG_TYPE:[CB(m_type,'^mt_'),cc], MFG_CODE:[MessageHandler(filters.TEXT&~filters.COMMAND,m_code),cc],
            MFG_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,m_qty),cc],
            MFG_PRI:[CB(m_pri,'^pri_'),cc], MFG_DL:[MessageHandler(filters.TEXT&~filters.COMMAND,m_dl),cc],
            MFG_WORKERS:[CB(m_workers,'^wr_'),cc], MFG_DETAILS:[MessageHandler(filters.TEXT&~filters.COMMAND,m_details),cc],
            MFG_DEL:[CB(m_del,'^del_'),cc],
            VST_TYPE:[MessageHandler(filters.TEXT&~filters.COMMAND,v_type),cc],
            VST_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,v_qty),cc],
            VST_LOGO:[MessageHandler(filters.TEXT&~filters.COMMAND,v_logo),cc],
            VST_DL:[MessageHandler(filters.TEXT&~filters.COMMAND,v_dl),cc],
            VST_WORKERS:[CB(v_workers,'^wr_'),cc],
            RDY_CODE:[MessageHandler(filters.TEXT&~filters.COMMAND,r_code),cc],
            RDY_NAME:[MessageHandler(filters.TEXT&~filters.COMMAND,r_name),cc],
            RDY_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,r_qty),cc],
            RDY_WH:[CB(r_wh,'^wh_'),cc], RDY_DEST:[CB(r_dest,'^dst_'),cc],
            RDY_WHO:[MessageHandler(filters.TEXT&~filters.COMMAND,r_who),cc],
            RDY_WORKER:[CB(r_worker,'^sw_'),cc],
            DRV_DRIVER:[CB(d_driver,'^sw_'),cc], DRV_CODE:[MessageHandler(filters.TEXT&~filters.COMMAND,d_code),cc],
            DRV_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,d_qty),cc],
            DRV_ADDR:[MessageHandler(filters.TEXT&~filters.COMMAND,d_addr),cc],
            DRV_PHONE:[MessageHandler(filters.TEXT&~filters.COMMAND,d_phone),cc],
            SHP_CO:[MessageHandler(filters.TEXT&~filters.COMMAND,s_co),cc],
            SHP_CODE:[MessageHandler(filters.TEXT&~filters.COMMAND,s_code),cc],
            SHP_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,s_qty),cc],
            SHP_CITY:[MessageHandler(filters.TEXT&~filters.COMMAND,s_city),cc],
            SHP_WORKER:[CB(s_worker,'^sw_'),cc],
            TRK_CODE:[MessageHandler(filters.TEXT&~filters.COMMAND,t_code),cc],
            TRK_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,t_qty),cc],
            TRK_DEST:[MessageHandler(filters.TEXT&~filters.COMMAND,t_dest),cc],
            TRK_PLATE:[MessageHandler(filters.TEXT&~filters.COMMAND,t_plate),cc],
            TRK_PHONE:[MessageHandler(filters.TEXT&~filters.COMMAND,t_phone),cc],
            TRK_WORKERS:[CB(t_workers,'^wr_'),cc],
            PC_DRIVER:[CB(p_driver,'^sw_'),cc], PC_TYPE:[MessageHandler(filters.TEXT&~filters.COMMAND,p_type),cc],
            PC_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,p_qty),cc],
            PC_PRINT:[MessageHandler(filters.TEXT&~filters.COMMAND,p_print),cc],
            CD_DRIVER:[CB(cd_driver,'^sw_'),cc], CD_CODE:[MessageHandler(filters.TEXT&~filters.COMMAND,cd_code),cc],
            CD_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,cd_qty),cc],
            CD_CLIENT:[MessageHandler(filters.TEXT&~filters.COMMAND,cd_client),cc],
            CS_CO:[MessageHandler(filters.TEXT&~filters.COMMAND,cs_co),cc],
            CS_CODE:[MessageHandler(filters.TEXT&~filters.COMMAND,cs_code),cc],
            CS_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,cs_qty),cc],
            CS_TRACK:[MessageHandler(filters.TEXT&~filters.COMMAND,cs_track),cc],
            CT_CODE:[MessageHandler(filters.TEXT&~filters.COMMAND,ct_code),cc],
            CT_QTY:[MessageHandler(filters.TEXT&~filters.COMMAND,ct_qty),cc],
            CT_PLATE:[MessageHandler(filters.TEXT&~filters.COMMAND,ct_plate),cc],
            CT_DNAME:[MessageHandler(filters.TEXT&~filters.COMMAND,ct_dname),cc],
            CT_STATUS:[CB(ct_status,'^cts_'),cc],
        },
        fallbacks=[CommandHandler('start',start),CommandHandler('menu',start),cc],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler('تقرير',cmd_report))
    app.add_handler(CommandHandler('report',cmd_report))
    print("🤖 البوت يعمل... اضغط Ctrl+C للإيقاف")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=='__main__':
    main()
