import asyncio, json, logging, os
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup,
                           ReplyKeyboardRemove, WebAppInfo)

logging.basicConfig(level=logging.INFO)
BASE = Path(__file__).parent
TOKEN = os.environ["BOT_TOKEN"]
ADMIN = int(os.getenv("ADMIN_ID", "0"))
URL = (os.getenv("WEBAPP_URL") or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
PORT = int(os.getenv("PORT", "8080"))

DATA = json.loads((BASE / "cars.json").read_text("utf-8"))
CARS = {c["id"]: c for c in DATA["cars"]}
D, SHOP = DATA["dict"], DATA["shop"]

# --- foydalanuvchilar (til) ---
UF = BASE / "users.json"
users = json.loads(UF.read_text()) if UF.exists() else {}
def save(): UF.write_text(json.dumps(users))
def L(uid): return users.get(str(uid), "uz")

T = {
    "uz": dict(
        pick_lang="Tilni tanlang / Выберите язык:",
        welcome="👋 Assalomu alaykum, <b>{n}</b>!\n<b>%s</b> avtosalonining rasmiy botiga xush kelibsiz.\n\n🚘 Katalogni mini ilovada ko'ring: rasmlar, narxlar va xususiyatlar." % SHOP["name"],
        catalog="🚘 Katalog", brands="🏷 Brend bo'yicha", prices="💰 Narx bo'yicha", credit="🧮 Kredit hisoblash",
        contact="📞 Aloqa", about="ℹ️ Biz haqimizda", lang="🌐 Til", back="⬅️ Orqaga",
        pick_brand="Brendni tanlang:", pick_price="Narx oralig'ini tanlang:", nothing="😕 Hozircha mashina topilmadi.",
        ask="📩 Ariza qoldirish", app="📱 Mini ilovada ochish", send_phone="Telefon raqamingizni yuboring 👇",
        share="📲 Raqamni yuborish", thanks="✅ Rahmat! Menejerimiz tez orada siz bilan bog'lanadi.",
        cancelled="Bekor qilindi.", km="km", y="yil",
        contact_txt="📞 <b>Aloqa</b>\n\nTelefon: {p}\n📍 {a}\n🕘 {h}\nMenejer: @{m}",
    ),
    "ru": dict(
        pick_lang="Tilni tanlang / Выберите язык:",
        welcome="👋 Здравствуйте, <b>{n}</b>!\nДобро пожаловать в официальный бот автосалона <b>%s</b>.\n\n🚘 Смотрите каталог в мини-приложении: фото, цены и характеристики." % SHOP["name"],
        catalog="🚘 Каталог", brands="🏷 По бренду", prices="💰 По цене", credit="🧮 Кредит-калькулятор",
        contact="📞 Контакты", about="ℹ️ О нас", lang="🌐 Язык", back="⬅️ Назад",
        pick_brand="Выберите бренд:", pick_price="Выберите диапазон цены:", nothing="😕 Пока ничего не найдено.",
        ask="📩 Оставить заявку", app="📱 Открыть в мини-приложении", send_phone="Отправьте свой номер телефона 👇",
        share="📲 Отправить номер", thanks="✅ Спасибо! Наш менеджер скоро свяжется с вами.",
        cancelled="Отменено.", km="км", y="г.",
        contact_txt="📞 <b>Контакты</b>\n\nТелефон: {p}\n📍 {a}\n🕘 {h}\nМенеджер: @{m}",
    ),
}
def both(k): return {T["uz"][k], T["ru"][k]}

RANGES = [(0, 15000), (15000, 25000), (25000, 35000), (35000, 10**9)]
def range_label(i):
    a, b = RANGES[i]
    return f"< ${b:,}" if a == 0 else (f"> ${a:,}" if b >= 10**9 else f"${a:,} – ${b:,}")

def menu(l):
    t = T[l]
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text=t["catalog"], web_app=WebAppInfo(url=f"{URL}/?lang={l}"))],
        [KeyboardButton(text=t["brands"]), KeyboardButton(text=t["prices"])],
        [KeyboardButton(text=t["credit"], web_app=WebAppInfo(url=f"{URL}/?lang={l}&tab=calc")),
         KeyboardButton(text=t["contact"])],
        [KeyboardButton(text=t["about"]), KeyboardButton(text=t["lang"])],
    ])

def lang_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")]])

def card(c, l):
    t = T[l]
    return (f"<b>{c['brand']} {c['name']}</b> · {c['year']} {t['y']}\n"
            f"💵 <b>${c['price']:,}</b>\n"
            f"🛣 {c['mileage']:,} {t['km']}\n"
            f"⛽ {D['fuel'][c['fuel']][l]} · ⚙️ {D['gearbox'][c['gearbox']][l]} · 🔧 {c['engine']}\n"
            f"🎨 {c['color'][l]}\n\n{c['desc'][l]}")

async def show_list(msg: Message, cars, l):
    if not cars:
        return await msg.answer(T[l]["nothing"])
    rows = [[InlineKeyboardButton(text=f"{c['brand']} {c['name']} · ${c['price']:,}", callback_data=f"c:{c['id']}")] for c in cars]
    await msg.answer("👇", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

class Lead(StatesGroup):
    phone = State()

dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: Message):
    if str(m.from_user.id) in users:
        l = L(m.from_user.id)
        await m.answer(T[l]["welcome"].format(n=m.from_user.full_name), reply_markup=menu(l))
    else:
        await m.answer(T["uz"]["pick_lang"], reply_markup=lang_kb())

@dp.callback_query(F.data.startswith("lang:"))
async def set_lang(c: CallbackQuery):
    l = c.data.split(":")[1]
    users[str(c.from_user.id)] = l; save()
    await c.message.delete()
    await c.message.answer(T[l]["welcome"].format(n=c.from_user.full_name), reply_markup=menu(l))
    await c.answer()

@dp.message(F.text.in_(both("lang")))
async def change_lang(m: Message):
    await m.answer(T["uz"]["pick_lang"], reply_markup=lang_kb())

@dp.message(F.text.in_(both("brands")))
async def by_brand(m: Message):
    l = L(m.from_user.id)
    brands = sorted({c["brand"] for c in CARS.values()})
    rows = [[InlineKeyboardButton(text=b, callback_data=f"b:{b}")] for b in brands]
    await m.answer(T[l]["pick_brand"], reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data.startswith("b:"))
async def brand_cb(c: CallbackQuery):
    b = c.data[2:]
    await show_list(c.message, [x for x in CARS.values() if x["brand"] == b], L(c.from_user.id))
    await c.answer()

@dp.message(F.text.in_(both("prices")))
async def by_price(m: Message):
    l = L(m.from_user.id)
    rows = [[InlineKeyboardButton(text=range_label(i), callback_data=f"p:{i}")] for i in range(len(RANGES))]
    await m.answer(T[l]["pick_price"], reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data.startswith("p:"))
async def price_cb(c: CallbackQuery):
    a, b = RANGES[int(c.data[2:])]
    await show_list(c.message, [x for x in CARS.values() if a <= x["price"] < b], L(c.from_user.id))
    await c.answer()

@dp.callback_query(F.data.startswith("c:"))
async def car_cb(c: CallbackQuery):
    l, car = L(c.from_user.id), CARS[int(c.data[2:])]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=T[l]["app"], web_app=WebAppInfo(url=f"{URL}/?lang={l}&car={car['id']}"))],
        [InlineKeyboardButton(text=T[l]["ask"], callback_data=f"l:{car['id']}")]])
    try:
        await c.message.answer_photo(car["images"][0], caption=card(car, l), reply_markup=kb)
    except Exception:
        await c.message.answer(card(car, l), reply_markup=kb)
    await c.answer()

# --- ariza (lead) ---
@dp.callback_query(F.data.startswith("l:"))
async def lead_start(c: CallbackQuery, state: FSMContext):
    l = L(c.from_user.id)
    await state.set_state(Lead.phone)
    await state.update_data(car=int(c.data[2:]))
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, keyboard=[
        [KeyboardButton(text=T[l]["share"], request_contact=True)], [KeyboardButton(text=T[l]["back"])]])
    await c.message.answer(T[l]["send_phone"], reply_markup=kb)
    await c.answer()

@dp.message(Lead.phone)
async def lead_phone(m: Message, state: FSMContext):
    l = L(m.from_user.id)
    if m.text in both("back"):
        await state.clear()
        return await m.answer(T[l]["cancelled"], reply_markup=menu(l))
    phone = m.contact.phone_number if m.contact else (m.text or "")
    car = CARS[(await state.get_data())["car"]]
    await state.clear()
    if ADMIN:
        u = m.from_user
        await m.bot.send_message(ADMIN, f"🔔 <b>Yangi ariza</b>\n👤 {u.full_name} (@{u.username or '-'}, id {u.id})\n"
                                        f"📞 {phone}\n🚘 {car['brand']} {car['name']} — ${car['price']:,}")
    await m.answer(T[l]["thanks"], reply_markup=menu(l))

@dp.message(F.text.in_(both("contact")))
async def contact(m: Message):
    l = L(m.from_user.id)
    await m.answer(T[l]["contact_txt"].format(p=SHOP["phone"], a=SHOP["address"][l], h=SHOP["hours"][l], m=SHOP["manager"]))
    await m.answer_location(SHOP["lat"], SHOP["lon"])

@dp.message(F.text.in_(both("about")))
async def about(m: Message):
    l = L(m.from_user.id)
    await m.answer(f"<b>{SHOP['name']}</b>\n\n{SHOP['about'][l]}")

# --- admin ---
@dp.message(Command("stats"), F.from_user.id == ADMIN)
async def stats(m: Message):
    await m.answer(f"👥 Users: {len(users)}\n🇺🇿 {sum(v == 'uz' for v in users.values())} | 🇷🇺 {sum(v == 'ru' for v in users.values())}")

@dp.message(Command("broadcast"), F.from_user.id == ADMIN)
async def broadcast(m: Message):
    text = (m.text or "").partition(" ")[2]
    if not text:
        return await m.answer("/broadcast matn")
    ok = 0
    for uid in list(users):
        try:
            await m.bot.send_message(int(uid), text); ok += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await m.answer(f"✅ {ok}/{len(users)}")

# --- veb-server (mini app) ---
async def index(_): return web.FileResponse(BASE / "webapp" / "index.html")
async def data(_): return web.json_response(DATA)
async def health(_): return web.Response(text="ok")

async def main():
    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/api/data", data), web.get("/health", health)])
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
