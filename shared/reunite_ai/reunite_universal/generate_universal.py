#!/usr/bin/env python3
"""
Reunite - universal synthetic dataset (fictional people, 10 disaster scenarios, 14 report languages).

Purpose
  1. Fine-tune a small LLM (e.g. IBM Granite 4.0 350M) to turn a free-text report in any language
     into one fixed JSON shape (schema.json).
  2. Train / evaluate the matching model: which missing report and which found report are the same person.

Every person is fictional. Scenarios borrow real places and disaster types so the text looks real.
Deterministic: same output every run.

Outputs (./reunite_universal):
  schema.json                 the extraction schema
  people.csv                  hidden truth about each fictional person (evaluation only)
  families.csv, family_members.csv   registered families (what the registration form stores)
  missing_reports.csv         free-text missing reports + form metadata
  found_reports.csv           free-text found reports (shelters, hospitals, public) + form metadata
  ground_truth.csv            record_id -> person_id (evaluation only, never load into the app)
  llm_train.jsonl / llm_val.jsonl / llm_test.jsonl   chat-format fine-tuning pairs (text -> JSON)
  README.md                   data card
"""
import csv, json, os, random
from datetime import datetime, timedelta

random.seed(2026)
OUT = "reunite_universal"
os.makedirs(OUT, exist_ok=True)

def N(*latin, native=None):
    """A name token: spelling variants in Latin script (first = standard) + optional native form."""
    return (list(latin), native)

# =============================================================================
# Vocabulary (canonical English -> each report language)
# =============================================================================
LANGS = ["en", "es", "fr", "pt", "it", "tr", "ar", "ja", "tl", "ht", "ur_r", "ur_s", "ne_r", "ne_s"]
LANG_LABEL = {"en": "English", "es": "Spanish", "fr": "French", "pt": "Portuguese", "it": "Italian", "tr": "Turkish",
              "ar": "Arabic", "ja": "Japanese", "tl": "Filipino (Taglish)", "ht": "Haitian Creole",
              "ur_r": "Urdu (Roman script)", "ur_s": "Urdu (Urdu script)", "ne_r": "Nepali (Roman script)", "ne_s": "Nepali (Devanagari)"}
SCRIPT_LANGS = {"ar", "ja", "ur_s", "ne_s"}

COLORS = ["red", "blue", "green", "yellow", "black", "white", "brown", "grey", "pink"]
COLOR_T = {
    "en": COLORS,
    "es": ["rojo", "azul", "verde", "amarillo", "negro", "blanco", "marrón", "gris", "rosa"],
    "fr": ["rouge", "bleu", "vert", "jaune", "noir", "blanc", "marron", "gris", "rose"],
    "pt": ["vermelho", "azul", "verde", "amarelo", "preto", "branco", "marrom", "cinza", "rosa"],
    "it": ["rosso", "blu", "verde", "giallo", "nero", "bianco", "marrone", "grigio", "rosa"],
    "tr": ["kırmızı", "mavi", "yeşil", "sarı", "siyah", "beyaz", "kahverengi", "gri", "pembe"],
    "ar": ["أحمر", "أزرق", "أخضر", "أصفر", "أسود", "أبيض", "بني", "رمادي", "وردي"],
    "ja": ["赤い", "青い", "緑の", "黄色い", "黒い", "白い", "茶色の", "灰色の", "ピンクの"],
    "tl": ["pula", "asul", "berde", "dilaw", "itim", "puti", "brown", "gray", "pink"],
    "ht": ["wouj", "ble", "vèt", "jòn", "nwa", "blan", "mawon", "gri", "woz"],
    "ur_r": ["laal", "neela", "hara", "peela", "kaala", "safaid", "bhoora", "surmai", "gulabi"],
    "ur_s": ["لال", "نیلا", "ہرا", "پیلا", "کالا", "سفید", "بھورا", "سرمئی", "گلابی"],
    "ne_r": ["rato", "nilo", "hariyo", "pahelo", "kalo", "seto", "khairo", "kharani", "gulabi"],
    "ne_s": ["रातो", "निलो", "हरियो", "पहेंलो", "कालो", "सेतो", "खैरो", "खरानी", "गुलाबी"],
}
ITEMS = ["shirt", "trousers", "dress", "scarf", "jacket", "cap"]
ITEM_T = {
    "en": ITEMS,
    "es": ["camisa", "pantalón", "vestido", "bufanda", "chaqueta", "gorra"],
    "fr": ["chemise", "pantalon", "robe", "foulard", "veste", "casquette"],
    "pt": ["camisa", "calça", "vestido", "lenço", "jaqueta", "boné"],
    "it": ["camicia", "pantaloni", "vestito", "sciarpa", "giacca", "cappellino"],
    "tr": ["gömlek", "pantolon", "elbise", "eşarp", "ceket", "şapka"],
    "ar": ["قميص", "بنطال", "فستان", "وشاح", "سترة", "قبعة"],
    "ja": ["シャツ", "ズボン", "ワンピース", "スカーフ", "ジャケット", "帽子"],
    "tl": ["shirt", "pantalon", "damit", "scarf", "jacket", "cap"],
    "ht": ["chemiz", "pantalon", "rad", "foula", "jakèt", "kaskèt"],
    "ur_r": ["qameez", "patloon", "frock", "dupatta", "jacket", "topi"],
    "ur_s": ["قمیض", "پتلون", "فراک", "دوپٹہ", "جیکٹ", "ٹوپی"],
    "ne_r": ["kameej", "pant", "frock", "scarf", "jacket", "topi"],
    "ne_s": ["कमिज", "पाइन्ट", "फ्रक", "स्कार्फ", "ज्याकेट", "टोपी"],
}
def garment(lang, c, i):
    col, item = COLOR_T[lang][c], ITEM_T[lang][i]
    return {"es": f"{item} de color {col}", "fr": f"{item} de couleur {col}", "pt": f"{item} de cor {col}",
            "it": f"{item} di colore {col}", "ar": f"{item} لونه {col}", "ht": f"{item} {col}",
            "ja": f"{col}{item}", "tl": f"{col} na {item}"}.get(lang, f"{col} {item}")

MARKS = ["scar on left arm", "birthmark on neck", "missing front tooth", "wears glasses",
         "walks with a limp", "mole on cheek", "tattoo on wrist", "uses a walking stick"]
MARK_T = {
    "en": MARKS,
    "es": ["cicatriz en el brazo izquierdo", "mancha de nacimiento en el cuello", "le falta un diente de adelante", "usa lentes", "cojea", "lunar en la mejilla", "tatuaje en la muñeca", "usa bastón"],
    "fr": ["cicatrice au bras gauche", "tache de naissance sur le cou", "dent de devant manquante", "porte des lunettes", "boite en marchant", "grain de beauté sur la joue", "tatouage au poignet", "marche avec une canne"],
    "pt": ["cicatriz no braço esquerdo", "marca de nascença no pescoço", "falta um dente da frente", "usa óculos", "manca", "pinta na bochecha", "tatuagem no pulso", "usa bengala"],
    "it": ["cicatrice sul braccio sinistro", "voglia sul collo", "manca un dente davanti", "porta gli occhiali", "zoppica", "neo sulla guancia", "tatuaggio sul polso", "usa il bastone"],
    "tr": ["sol kolunda yara izi", "boynunda doğum lekesi", "ön dişi eksik", "gözlük takıyor", "topallıyor", "yanağında ben", "bileğinde dövme", "baston kullanıyor"],
    "ar": ["ندبة في الذراع اليسرى", "وحمة في الرقبة", "سن أمامي مفقود", "يرتدي نظارات", "يعرج", "شامة على الخد", "وشم على المعصم", "يستخدم عكازاً"],
    "ja": ["左腕に傷跡", "首にあざ", "前歯が一本ない", "眼鏡をかけている", "足を引きずって歩く", "頬にほくろ", "手首にタトゥー", "杖を使っている"],
    "tl": ["peklat sa kaliwang braso", "balat sa leeg", "bungi sa harap", "naka-salamin", "paika-ika maglakad", "nunal sa pisngi", "tattoo sa pulso", "may tungkod"],
    "ht": ["mak blese sou bra goch", "mak nesans sou kou", "manke yon dan devan", "mete linèt", "bwete", "grenn bote sou machwè", "tatou sou ponyèt", "mache ak baton"],
    "ur_r": ["baayen baazu par zakhm ka nishan", "gardan par paidaishi nishan", "aage ka daant toota hua", "ainak lagate hain", "langra kar chalte hain", "gaal par til", "kalai par tattoo", "chhari se chalte hain"],
    "ur_s": ["بائیں بازو پر زخم کا نشان", "گردن پر پیدائشی نشان", "آگے کا دانت ٹوٹا ہوا", "عینک لگاتے ہیں", "لنگڑا کر چلتے ہیں", "گال پر تل", "کلائی پر ٹیٹو", "چھڑی سے چلتے ہیں"],
    "ne_r": ["debre haat ma chot ko daag", "ghanti ma janmadaag", "agadi ko daant chhaina", "chasma lagauchha", "khochyaudai hidchha", "gala ma kothi", "naadi ma tattoo", "lauro tekchha"],
    "ne_s": ["देब्रे हातमा चोटको दाग", "घाँटीमा जन्मदाग", "अगाडिको दाँत छैन", "चस्मा लगाउनुहुन्छ", "खोच्याउँदै हिँड्नुहुन्छ", "गालामा कोठी", "नाडीमा ट्याटु", "लौरो टेकेर हिँड्नुहुन्छ"],
}
MEDICAL = ["diabetes", "dementia", "heart condition", "asthma", "pregnant", "epilepsy"]
MED_T = {
    "en": ["diabetes", "dementia", "a heart condition", "asthma", "pregnant", "epilepsy"],
    "es": ["diabetes", "demencia", "problemas del corazón", "asma", "embarazada", "epilepsia"],
    "fr": ["diabète", "démence", "problème cardiaque", "asthme", "enceinte", "épilepsie"],
    "pt": ["diabetes", "demência", "problema no coração", "asma", "grávida", "epilepsia"],
    "it": ["diabete", "demenza", "problemi cardiaci", "asma", "incinta", "epilessia"],
    "tr": ["şeker hastası", "demans", "kalp hastası", "astım", "hamile", "epilepsi"],
    "ar": ["السكري", "الخرف", "مرض القلب", "الربو", "حامل", "الصرع"],
    "ja": ["糖尿病", "認知症", "心臓病", "ぜんそく", "妊娠中", "てんかん"],
    "tl": ["diabetes", "makakalimutin", "sakit sa puso", "hika", "buntis", "epilepsy"],
    "ht": ["dyabèt", "pèdi memwa", "maladi kè", "opresyon", "ansent", "malkadi"],
    "ur_r": ["sugar", "bhoolne ki bimari", "dil ki bimari", "dama", "hamla", "mirgi"],
    "ur_s": ["شوگر", "بھولنے کی بیماری", "دل کی بیماری", "دمہ", "حاملہ", "مرگی"],
    "ne_r": ["chini rog", "birsane rog", "mutu rog", "dam", "garbhavati", "chhare rog"],
    "ne_s": ["चिनी रोग", "बिर्सने रोग", "मुटु रोग", "दम", "गर्भवती", "छारे रोग"],
}
LANGNAME_T = {
    "es": {"Spanish": "español", "Nahuatl": "náhuatl", "Mixtec": "mixteco", "English": "inglés"},
    "fr": {"French": "français", "Haitian Creole": "créole haïtien", "Arabic": "arabe", "Tamazight": "tamazight", "English": "anglais"},
    "pt": {"Portuguese": "português", "English": "inglês"},
    "it": {"Italian": "italiano", "English": "inglese"},
    "tr": {"Turkish": "Türkçe", "Arabic": "Arapça", "Kurdish": "Kürtçe", "English": "İngilizce"},
    "ar": {"Arabic": "العربية", "Tamazight": "الأمازيغية", "French": "الفرنسية", "English": "الإنجليزية"},
    "ja": {"Japanese": "日本語", "English": "英語"},
    "ht": {"Haitian Creole": "kreyòl", "French": "franse", "English": "angle"},
    "ur_s": {"Urdu": "اردو", "Sindhi": "سندھی", "Saraiki": "سرائیکی", "English": "انگریزی"},
    "ne_s": {"Nepali": "नेपाली", "Tamang": "तामाङ", "Sherpa": "शेर्पा", "Tibetan": "तिब्बती", "English": "अंग्रेजी"},
}
# person nouns: man, woman, boy, girl
NOUN = {
    "en": ["man", "woman", "boy", "girl"], "es": ["hombre", "mujer", "niño", "niña"], "fr": ["homme", "femme", "garçon", "fille"],
    "pt": ["homem", "mulher", "menino", "menina"], "it": ["uomo", "donna", "bambino", "bambina"],
    "tr": ["erkek", "kadın", "erkek çocuk", "kız çocuk"], "ar": ["رجل", "امرأة", "ولد", "بنت"], "ja": ["男性", "女性", "男の子", "女の子"],
    "tl": ["lalaki", "babae", "batang lalaki", "batang babae"], "ht": ["gason", "fanm", "ti gason", "ti fi"],
    "ur_r": ["aadmi", "aurat", "larka", "larki"], "ur_s": ["مرد", "عورت", "لڑکا", "لڑکی"],
    "ne_r": ["purush", "mahila", "keta", "keti"], "ne_s": ["पुरुष", "महिला", "केटा", "केटी"],
}
T = {  # sentence templates
    "en": dict(mi="Looking for {name}, {age} years old.", mig="Looking for {name}, {art} {age}-year-old {noun}.", seen="Last seen in {place}.",
               wear="Wearing {c}.", mark="{m}.", med="Has {x}.", speak="Speaks {l}.", fi="Found {art} {noun}, about {age} years old.",
               fname="Says their name is {name}.", fnoname="Cannot say their name.", fplace="Found near {place}.", fnow="Now at {s}.", hurt="Injured.",
               fill=["Please help.", "We are very worried.", "Any information please call."]),
    "es": dict(mi="Busco a {name}, de {age} años.", mig="Busco a {name}, {noun} de {age} años.", seen="Se le vio por última vez en {place}.",
               wear="Llevaba {c}.", mark="Señas: {m}.", med="Padece {x}.", speak="Habla {l}.", fi="Persona encontrada: {noun} de unos {age} años.",
               fname="Dice llamarse {name}.", fnoname="No sabe decir su nombre.", fplace="Lugar: cerca de {place}.", fnow="Ahora en {s}.", hurt="Tiene heridas.",
               fill=["Por favor ayúdenme.", "Estamos muy preocupados."]),
    "fr": dict(mi="Je cherche {name}, {age} ans.", mig="Je cherche {name}, {noun} de {age} ans.", seen="Vu pour la dernière fois à {place}.",
               wear="Portait {c}.", mark="Signe particulier : {m}.", med="Problème de santé : {x}.", speak="Parle {l}.", fi="Personne trouvée : {noun}, environ {age} ans.",
               fname="Dit s'appeler {name}.", fnoname="Ne peut pas dire son nom.", fplace="Lieu : près de {place}.", fnow="Actuellement à {s}.", hurt="Blessé.",
               fill=["Aidez-nous s'il vous plaît.", "Nous sommes très inquiets."]),
    "pt": dict(mi="Procuro {name}, {age} anos.", mig="Procuro {name}, {noun} de {age} anos.", seen="Visto pela última vez em {place}.",
               wear="Usava {c}.", mark="Sinais: {m}.", med="Problema de saúde: {x}.", speak="Fala {l}.", fi="Pessoa encontrada: {noun}, cerca de {age} anos.",
               fname="Diz que se chama {name}.", fnoname="Não sabe dizer o nome.", fplace="Local: perto de {place}.", fnow="Agora em {s}.", hurt="Tem ferimentos.",
               fill=["Por favor, ajudem.", "Estamos muito preocupados."]),
    "it": dict(mi="Cerco {name}, {age} anni.", mig="Cerco {name}, {noun} di {age} anni.", seen="Visto l'ultima volta a {place}.",
               wear="Indossava {c}.", mark="Segni particolari: {m}.", med="Problemi di salute: {x}.", speak="Parla {l}.", fi="Persona trovata: {noun}, circa {age} anni.",
               fname="Dice di chiamarsi {name}.", fnoname="Non sa dire il suo nome.", fplace="Luogo: vicino a {place}.", fnow="Ora presso {s}.", hurt="Ha delle ferite.",
               fill=["Vi prego, aiutateci.", "Siamo molto preoccupati."]),
    "tr": dict(mi="{name} kayıp, {age} yaşında.", mig="{name} kayıp, {age} yaşında {noun}.", seen="En son görüldüğü yer: {place}.",
               wear="Üzerinde {c} vardı.", mark="Belirgin işaret: {m}.", med="Sağlık durumu: {x}.", speak="Konuştuğu dil: {l}.", fi="Bulunan kişi: {noun}, yaklaşık {age} yaşında.",
               fname="Adının {name} olduğunu söylüyor.", fnoname="Adını söyleyemiyor.", fplace="Yer: {place} yakınları.", fnow="Şu an: {s}.", hurt="Yaralı.",
               fill=["Lütfen yardım edin.", "Çok endişeliyiz."]),
    "ar": dict(mi="أبحث عن {name}، العمر {age} سنة.", mig="أبحث عن {name}، {noun}، العمر {age} سنة.", seen="شوهد آخر مرة في {place}.",
               wear="الملابس: {c}.", mark="علامة مميزة: {m}.", med="حالة صحية: {x}.", speak="اللغة: {l}.", fi="تم العثور على {noun}، العمر حوالي {age} سنة.",
               fname="الاسم حسب قوله: {name}.", fnoname="لا يستطيع ذكر اسمه.", fplace="المكان: قرب {place}.", fnow="حالياً في {s}.", hurt="مصاب.",
               fill=["أرجو المساعدة.", "نحن قلقون جداً."]),
    "ja": dict(mi="{name}を探しています。{age}歳です。", mig="{name}を探しています。{age}歳の{noun}です。", seen="最後に見たのは{place}です。",
               wear="{c}を身につけていました。", mark="特徴：{m}。", med="持病：{x}。", speak="話す言語：{l}。", fi="{noun}を保護しました。{age}歳くらいです。",
               fname="名前は{name}と言っています。", fnoname="名前は言えません。", fplace="場所：{place}付近。", fnow="現在{s}にいます。", hurt="けがをしています。",
               fill=["どうか助けてください。", "とても心配しています。"]),
    "tl": dict(mi="Hinahanap ko si {name}, {age} years old.", mig="Hinahanap ko si {name}, {noun}, {age} years old.", seen="Huling nakita sa {place}.",
               wear="Suot niya ang {c}.", mark="Palatandaan: {m}.", med="May sakit siya: {x}.", speak="Nagsasalita ng {l}.", fi="May nakitang {noun}, mga {age} years old.",
               fname="Ang pangalan daw ay {name}.", fnoname="Hindi masabi ang pangalan.", fplace="Lugar: malapit sa {place}.", fnow="Nasa {s} na ngayon.", hurt="May sugat.",
               fill=["Pakiusap, tulungan niyo kami.", "Sobrang nag-aalala kami."]),
    "ht": dict(mi="M ap chèche {name}, {age} an.", mig="M ap chèche {name}, yon {noun} {age} an.", seen="Dènye fwa yo te wè l se {place}.",
               wear="Li te mete {c}.", mark="Siy: {m}.", med="Pwoblèm sante: {x}.", speak="Li pale {l}.", fi="Nou jwenn yon {noun}, anviwon {age} an.",
               fname="Li di non li se {name}.", fnoname="Li pa ka di non li.", fplace="Kote: toupre {place}.", fnow="Kounye a li nan {s}.", hurt="Li blese.",
               fill=["Tanpri ede nou.", "Nou enkyete anpil."]),
    "ur_r": dict(mi="{name} lapata hain, umar {age} saal.", mig="{name} lapata hain, {noun}, umar {age} saal.", seen="Aakhri baar {place} mein dekha.",
               wear="{c} pehna tha.", mark="Nishani: {m}.", med="Bimari: {x}.", speak="Zubaan: {l}.", fi="Ek {noun} mila hai, umar taqreeban {age} saal.",
               fname="Naam {name} batate hain.", fnoname="Naam nahi bata sakte.", fplace="Jagah: {place} ke qareeb.", fnow="Abhi {s} mein hain.", hurt="Zakhmi hain.",
               fill=["Please madad karein.", "Hum bohat pareshan hain."]),
    "ur_s": dict(mi="{name} لاپتہ ہیں، عمر {age} سال۔", mig="{name} لاپتہ ہیں، {noun}، عمر {age} سال۔", seen="آخری بار {place} میں دیکھا گیا۔",
               wear="{c} پہنا تھا۔", mark="نشانی: {m}۔", med="بیماری: {x}۔", speak="زبان: {l}۔", fi="ایک {noun} ملا ہے، عمر تقریباً {age} سال۔",
               fname="نام {name} بتاتے ہیں۔", fnoname="نام نہیں بتا سکتے۔", fplace="جگہ: {place} کے قریب۔", fnow="ابھی {s} میں ہیں۔", hurt="زخمی ہیں۔",
               fill=["براہ کرم مدد کریں۔", "ہم بہت پریشان ہیں۔"]),
    "ne_r": dict(mi="{name} harayeko chha, umer {age} barsa.", mig="{name} harayeko chha, {noun}, umer {age} barsa.", seen="Antim patak {place} ma dekhiyo.",
               wear="{c} lagayeko thiyo.", mark="Chinha: {m}.", med="Swasthya: {x}.", speak="Bhasa: {l}.", fi="Euta {noun} bhetiyo, umer lagbhag {age} barsa.",
               fname="Naam {name} bhanchha.", fnoname="Naam bhanna sakdaina.", fplace="Thau: {place} najik.", fnow="Ahile {s} ma hunuhunchha.", hurt="Ghaite chha.",
               fill=["Kripaya sahayog garnus.", "Hami dherai chintit chhau."]),
    "ne_s": dict(mi="{name} हराउनुभएको छ, उमेर {age} वर्ष।", mig="{name} हराउनुभएको छ, {noun}, उमेर {age} वर्ष।", seen="अन्तिम पटक {place} मा देखिनुभयो।",
               wear="{c} लगाएको थियो।", mark="चिन्ह: {m}।", med="स्वास्थ्य: {x}।", speak="भाषा: {l}।", fi="एक जना {noun} भेटिनुभयो, उमेर करिब {age} वर्ष।",
               fname="नाम {name} भन्नुहुन्छ।", fnoname="नाम भन्न सक्नुहुन्न।", fplace="ठाउँ: {place} नजिक।", fnow="अहिले {s} मा हुनुहुन्छ।", hurt="घाइते हुनुहुन्छ।",
               fill=["कृपया सहयोग गर्नुहोस्।", "हामी धेरै चिन्तित छौं।"]),
}
LIST_SEP = {"ja": "、", "ar": "، ", "ur_s": "، "}

# =============================================================================
# Countries / scenarios
# =============================================================================
C = {}
C["PK"] = dict(
    scenario="Monsoon floods, Sindh (Pakistan)", hazard="flood", start=datetime(2022, 8, 25, 6, 0), span_h=24 * 8, phone="+92", split="train",
    report_langs={"en": .3, "ur_r": .35, "ur_s": .35}, shelter_langs={"en": .5, "ur_s": .5},
    spoken=[("Sindhi", .95), ("Urdu", .55), ("Saraiki", .12)],
    male=[N("Muhammad", "Mohammad", "Mohammed", "Mohd", native="محمد"), N("Ahmed", "Ahmad", native="احمد"), N("Ali", native="علی"),
          N("Hussain", "Hussein", "Husain", native="حسین"), N("Ghulam Rasool", "Gulam Rasul", native="غلام رسول"), N("Allah Dino", "Allahdino", native="اللہ ڈنو"),
          N("Khuda Bux", "Khuda Bakhsh", native="خدا بخش"), N("Bashir", "Basheer", native="بشیر"), N("Qasim", "Kasim", native="قاسم"), N("Yousuf", "Yusuf", "Yousaf", native="یوسف")],
    female=[N("Fatima", "Fatma", "Fatimah", native="فاطمہ"), N("Ayesha", "Aisha", "Aysha", native="عائشہ"), N("Zainab", "Zaynab", native="زینب"),
            N("Rukhsana", "Rukhsanah", native="رخسانہ"), N("Nasreen", "Nasrin", native="نسرین"), N("Shazia", "Shaziya", native="شازیہ"),
            N("Khadija", "Khadijah", native="خدیجہ"), N("Parveen", "Perveen", "Parvin", native="پروین"), N("Hajani", native="حاجانی")],
    family=[N("Solangi", native="سولنگی"), N("Chandio", "Chandiyo", native="چانڈیو"), N("Jatoi", native="جتوئی"), N("Brohi", native="بروہی"),
            N("Mallah", "Malah", native="ملاح"), N("Khoso", native="کھوسو"), N("Panhwar", native="پنہور"), N("Jamali", native="جمالی"), N("Memon", native="میمن")],
    nicks=["Guddu", "Pappu", "Munni", "Bablu", "Gudiya", "Raju", "Sonu"],
    places={"Johi": (26.69, 67.61, "جوہی"), "Dadu": (26.73, 67.78, "دادو"), "Mehar": (27.18, 67.82, "میہڑ"), "Sehwan": (26.43, 67.86, "سیہون"),
            "Khairpur Nathan Shah": (27.09, 67.73, "خیرپور ناتھن شاہ"), "Radhan": (27.20, 67.95, "رادھن")},
    sites=[("Dadu Civil Hospital", "دادو سول اسپتال", 26.73, 67.78, "hospital"), ("Sehwan Relief Camp", "سیہون ریلیف کیمپ", 26.42, 67.87, "shelter"),
           ("Hyderabad Relief Camp", "حیدرآباد ریلیف کیمپ", 25.39, 68.33, "shelter"), ("Sukkur Shelter Camp", "سکھر شیلٹر کیمپ", 27.70, 68.86, "shelter")],
)
C["NP"] = dict(
    scenario="Glacier flash flood, Rasuwa and Nuwakot (Nepal)", hazard="flash flood", start=datetime(2026, 8, 26, 8, 30), span_h=4, phone="+977", split="train",
    report_langs={"en": .3, "ne_r": .35, "ne_s": .35}, shelter_langs={"en": .5, "ne_s": .5},
    spoken=[("Nepali", .95), ("Tamang", .35), ("Sherpa", .1), ("Tibetan", .08)],
    male=[N("Ram", "Raam", native="राम"), N("Hari", native="हरि"), N("Krishna", "Krishn", native="कृष्ण"), N("Bishnu", "Vishnu", native="बिष्णु"),
          N("Pemba", "Pempa", native="पेम्बा"), N("Dawa", "Dawaa", native="दावा"), N("Tenzing", "Tenzin", native="तेन्जिङ"), N("Pasang", "Phasang", native="पासाङ")],
    female=[N("Sita", "Seeta", native="सीता"), N("Gita", "Geeta", native="गीता"), N("Laxmi", "Lakshmi", native="लक्ष्मी"), N("Kamala", "Kamla", native="कमला"),
            N("Sabitri", "Savitri", native="सावित्री"), N("Maya", native="माया"), N("Pema", "Pemma", native="पेमा"), N("Dolma", "Dolkar", native="डोल्मा")],
    family=[N("Tamang", native="तामाङ"), N("Gurung", native="गुरुङ"), N("Ghale", "Ghaley", native="घले"), N("Lama", native="लामा"),
            N("Shrestha", "Shresta", native="श्रेष्ठ"), N("Thapa", native="थापा"), N("Paudel", "Poudel", native="पौडेल"), N("Ghimire", "Ghimirey", native="घिमिरे")],
    nicks=["Kancha", "Kanchhi", "Saila", "Maili", "Babu", "Nani"],
    places={"Syabrubesi": (28.16, 85.34, "स्याब्रुबेसी"), "Timure": (28.23, 85.36, "टिमुरे"), "Dhunche": (28.11, 85.30, "धुन्चे"),
            "Betrawati": (27.97, 85.18, "बेत्रावती"), "Bidur": (27.92, 85.15, "विदुर"), "Devighat": (27.88, 85.13, "देवीघाट")},
    sites=[("Dhunche District Hospital", "धुन्चे जिल्ला अस्पताल", 28.11, 85.30, "hospital"), ("Trishuli Hospital", "त्रिशूली अस्पताल", 27.90, 85.15, "hospital"),
           ("Betrawati Relief Camp", "बेत्रावती राहत शिविर", 27.97, 85.18, "shelter"), ("Bir Hospital Kathmandu", "वीर अस्पताल काठमाडौं", 27.70, 85.31, "hospital")],
)
C["MX"] = dict(
    scenario="Hurricane landfall, Guerrero (Mexico)", hazard="hurricane", start=datetime(2023, 10, 25, 1, 0), span_h=36, phone="+52", split="train",
    report_langs={"es": .9, "en": .1}, shelter_langs={"es": 1.0},
    spoken=[("Spanish", 1.0), ("Nahuatl", .06), ("Mixtec", .05)],
    male=[N("Jose", native="José"), N("Juan"), N("Luis"), N("Miguel"), N("Jesus", native="Jesús"), N("Francisco"), N("Raul", native="Raúl")],
    female=[N("Maria", "Ma.", native="María"), N("Guadalupe"), N("Rosa"), N("Juana"), N("Carmen"), N("Josefina"), N("Veronica", native="Verónica")],
    family=[N("Hernandez", native="Hernández"), N("Garcia", native="García"), N("Martinez", native="Martínez"), N("Lopez", native="López"),
            N("Gonzalez", native="González"), N("Rodriguez", native="Rodríguez"), N("Perez", native="Pérez")],
    double_surname=True, nicks=["Pepe", "Chuy", "Pancho", "Lupita", "Chepina", "Rosita"],
    places={"Acapulco": (16.85, -99.88, None), "Coyuca de Benitez": (17.01, -100.09, "Coyuca de Benítez"), "Chilpancingo": (17.55, -99.50, None),
            "Tecpan": (17.22, -100.63, "Tecpan de Galeana"), "Pie de la Cuesta": (16.88, -99.98, None)},
    sites=[("Hospital General de Acapulco", None, 16.86, -99.88, "hospital"), ("Albergue Unidad Deportiva Acapulco", None, 16.87, -99.87, "shelter"),
           ("Albergue Chilpancingo Centro", None, 17.55, -99.50, "shelter"), ("Cruz Roja Coyuca", None, 17.01, -100.09, "shelter")],
)
C["BR"] = dict(
    scenario="River floods, Rio Grande do Sul (Brazil)", hazard="flood", start=datetime(2024, 5, 3, 7, 0), span_h=24 * 5, phone="+55", split="train",
    report_langs={"pt": .9, "en": .1}, shelter_langs={"pt": 1.0},
    spoken=[("Portuguese", 1.0)],
    male=[N("Joao", native="João"), N("Jose", native="José"), N("Antonio", native="Antônio"), N("Francisco"), N("Carlos"), N("Paulo"), N("Sebastiao", native="Sebastião")],
    female=[N("Maria"), N("Ana"), N("Francisca"), N("Antonia", native="Antônia"), N("Conceicao", native="Conceição"), N("Luzia"), N("Rosangela", native="Rosângela")],
    family=[N("da Silva", "Silva"), N("dos Santos", "Santos"), N("Oliveira"), N("Souza", "Sousa"), N("Pereira"), N("Ferreira"), N("Lima")],
    nicks=["Ze", "Toninho", "Chico", "Tiao", "Nena"],
    places={"Porto Alegre": (-30.03, -51.23, None), "Canoas": (-29.92, -51.18, None), "Eldorado do Sul": (-30.08, -51.62, None),
            "Sao Leopoldo": (-29.76, -51.15, "São Leopoldo"), "Guaiba": (-30.11, -51.33, "Guaíba")},
    sites=[("Hospital de Pronto Socorro Porto Alegre", None, -30.04, -51.21, "hospital"), ("Abrigo Ginasio Tesourinha", None, -30.04, -51.22, "shelter"),
           ("Abrigo ULBRA Canoas", None, -29.92, -51.17, "shelter"), ("Abrigo Sao Leopoldo Centro", None, -29.76, -51.15, "shelter")],
)
C["IT"] = dict(
    scenario="Night earthquake, central Apennines (Italy)", hazard="earthquake", start=datetime(2016, 8, 24, 3, 36), span_h=2, phone="+39", split="train",
    report_langs={"it": .9, "en": .1}, shelter_langs={"it": 1.0},
    spoken=[("Italian", 1.0), ("English", .1)],
    male=[N("Giuseppe"), N("Giovanni"), N("Antonio"), N("Francesco"), N("Mario"), N("Luigi"), N("Nicola")],
    female=[N("Maria"), N("Anna"), N("Giuseppina"), N("Rosa"), N("Angela"), N("Lucia"), N("Assunta")],
    family=[N("Rossi"), N("Russo"), N("Ferrari"), N("Esposito"), N("Bianchi"), N("De Luca", "Deluca"), N("Romano"), N("Di Marco", "Dimarco")],
    nicks=["Peppe", "Gianni", "Tonino", "Gino", "Pina", "Nuccia"],
    places={"Amatrice": (42.63, 13.29, None), "Accumoli": (42.69, 13.25, None), "Norcia": (42.79, 13.09, None), "Arquata del Tronto": (42.77, 13.30, None)},
    sites=[("Ospedale di Rieti", None, 42.40, 12.86, "hospital"), ("Tendopoli Amatrice", None, 42.63, 13.29, "shelter"),
           ("Palestra comunale Norcia", None, 42.79, 13.09, "shelter"), ("Ospedale di Ascoli Piceno", None, 42.85, 13.58, "hospital")],
)
C["HT"] = dict(
    scenario="Earthquake, southern peninsula (Haiti)", hazard="earthquake", start=datetime(2021, 8, 14, 8, 29), span_h=3, phone="+509", split="train",
    report_langs={"ht": .45, "fr": .45, "en": .1}, shelter_langs={"fr": .7, "ht": .3},
    spoken=[("Haitian Creole", 1.0), ("French", .3)],
    male=[N("Jean-Baptiste", "Jean Baptiste", "Jean-Batiste"), N("Pierre"), N("Jean-Claude", "Jean Claude"), N("Joseph", "Jozef"), N("Wilner"), N("Jacques", "Jak")],
    female=[N("Marie-Claude", "Marie Claude"), N("Marie-Ange", "Marie Ange"), N("Rose-Marie", "Rosemarie"), N("Guerline", "Gerline"),
            N("Mirlande"), N("Nadege", native="Nadège")],
    family=[N("Jean"), N("Pierre"), N("Louis"), N("Joseph"), N("Charles"), N("Saint-Fleur", "St Fleur", "Saint Fleur"), N("Desir", native="Désir")],
    nicks=["Ti Jean", "Ti Pierre", "Nana", "Bebe", "Ti Fi"],
    places={"Les Cayes": (18.20, -73.75, None), "Jeremie": (18.65, -74.12, "Jérémie"), "Port-Salut": (18.08, -73.92, None), "Camp-Perrin": (18.32, -73.86, None),
            "Maniche": (18.34, -73.78, None)},
    sites=[("Hopital Immaculee Conception Les Cayes", "Hôpital Immaculée Conception Les Cayes", 18.20, -73.75, "hospital"),
           ("Camp Parc Larco Les Cayes", None, 18.19, -73.76, "shelter"), ("Hopital Saint-Antoine Jeremie", "Hôpital Saint-Antoine Jérémie", 18.65, -74.11, "hospital"),
           ("Abri Ecole Nationale Camp-Perrin", "Abri École Nationale Camp-Perrin", 18.32, -73.86, "shelter")],
)
C["JP"] = dict(
    scenario="New Year earthquake, Noto Peninsula (Japan)", hazard="earthquake", start=datetime(2024, 1, 1, 16, 10), span_h=3, phone="+81", split="train",
    report_langs={"ja": .85, "en": .15}, shelter_langs={"ja": 1.0},
    spoken=[("Japanese", 1.0), ("English", .05)], japanese=True,
    male=[N("Haruto", native="陽翔"), N("Ren", native="蓮"), N("Sota", "Souta", native="颯太"), N("Hiroshi", native="博"), N("Takeshi", native="武"),
          N("Kenji", native="健二"), N("Shigeru", native="茂")],
    female=[N("Yui", native="結衣"), N("Hina", native="陽菜"), N("Aoi", native="葵"), N("Kazuko", native="和子"), N("Keiko", native="恵子"),
            N("Sachiko", native="幸子"), N("Yoko", "Youko", native="洋子")],
    family=[N("Sato", "Satou", "Satoh", native="佐藤"), N("Suzuki", native="鈴木"), N("Takahashi", native="高橋"), N("Tanaka", native="田中"),
            N("Watanabe", native="渡辺"), N("Ito", "Itou", "Itoh", native="伊藤"), N("Yamamoto", native="山本"), N("Nakamura", native="中村")],
    nicks=[],
    places={"Wajima": (37.39, 136.90, "輪島市"), "Suzu": (37.44, 137.26, "珠洲市"), "Anamizu": (37.23, 136.91, "穴水町"), "Noto": (37.31, 137.15, "能登町"),
            "Nanao": (37.04, 136.97, "七尾市")},
    sites=[("Wajima Middle School Shelter", "輪島中学校避難所", 37.39, 136.90, "shelter"), ("Suzu City Hall Shelter", "珠洲市役所避難所", 37.44, 137.26, "shelter"),
           ("Kanazawa University Hospital", "金沢大学附属病院", 36.56, 136.66, "hospital"), ("Nanao Gymnasium Shelter", "七尾市総合体育館避難所", 37.04, 136.97, "shelter")],
)
C["TR"] = dict(
    scenario="Earthquake, Hatay and Kahramanmaras (Turkiye)", hazard="earthquake", start=datetime(2023, 2, 6, 4, 17), span_h=12, phone="+90", split="train",
    report_langs={"tr": .85, "en": .15}, shelter_langs={"tr": 1.0},
    spoken=[("Turkish", 1.0), ("Arabic", .2), ("Kurdish", .12)],
    male=[N("Mehmet", "Mehmed"), N("Mustafa"), N("Ahmet"), N("Huseyin", "Husein", native="Hüseyin"), N("Ali"), N("Ibrahim", native="İbrahim"), N("Omer", native="Ömer")],
    female=[N("Ayse", "Aishe", native="Ayşe"), N("Fatma"), N("Emine"), N("Zeynep", "Zeinep"), N("Hatice"), N("Elif"), N("Sukran", native="Şükran")],
    family=[N("Yilmaz", native="Yılmaz"), N("Kaya"), N("Demir"), N("Celik", native="Çelik"), N("Sahin", native="Şahin"), N("Ozturk", native="Öztürk"), N("Aydin", native="Aydın")],
    nicks=[],
    places={"Antakya": (36.20, 36.16, None), "Kahramanmaras": (37.58, 36.93, "Kahramanmaraş"), "Iskenderun": (36.59, 36.17, "İskenderun"),
            "Adiyaman": (37.76, 38.28, "Adıyaman"), "Defne": (36.19, 36.14, None)},
    sites=[("Adana Sehir Hastanesi", "Adana Şehir Hastanesi", 37.05, 35.30, "hospital"), ("Antakya Cadirkent", "Antakya Çadırkent", 36.21, 36.17, "shelter"),
           ("Iskenderun Devlet Hastanesi", "İskenderun Devlet Hastanesi", 36.59, 36.17, "hospital"), ("Kahramanmaras Cadirkent", "Kahramanmaraş Çadırkent", 37.58, 36.92, "shelter")],
)
C["MA"] = dict(
    scenario="Night earthquake, Al Haouz (Morocco)", hazard="earthquake", start=datetime(2023, 9, 8, 23, 11), span_h=3, phone="+212", split="test",
    report_langs={"ar": .45, "fr": .45, "en": .1}, shelter_langs={"ar": .5, "fr": .5},
    spoken=[("Tamazight", .8), ("Arabic", .9), ("French", .25)],
    male=[N("Mohamed", "Mohammed", "Mhamed", native="محمد"), N("Youssef", "Yousef", "Youssouf", native="يوسف"), N("Brahim", "Ibrahim", native="إبراهيم"),
          N("Hassan", "Hasan", native="حسن"), N("Lahcen", "Lahoucine", native="لحسن"), N("Omar", native="عمر"), N("Abdellah", "Abdallah", native="عبد الله")],
    female=[N("Fatima", "Fatma", "Fatéma", native="فاطمة"), N("Khadija", "Khadidja", native="خديجة"), N("Aicha", "Aïcha", "Aisha", native="عائشة"),
            N("Zineb", "Zaynab", native="زينب"), N("Itto", "Ito", native="إطو"), N("Malika", native="مليكة"), N("Rachida", native="رشيدة")],
    family=[N("Ait Ali", "Aït Ali", native="آيت علي"), N("El Amrani", "Amrani", native="العمراني"), N("Benali", "Ben Ali", native="بن علي"),
            N("Bouzid", native="بوزيد"), N("El Idrissi", "Idrissi", native="الإدريسي"), N("Ouchen", native="أوشن"), N("Ait Brahim", "Aït Brahim", native="آيت إبراهيم")],
    nicks=[],
    places={"Amizmiz": (31.22, -8.24, "أمزميز"), "Talat N'Yaaqoub": (30.99, -8.18, "تالات نيعقوب"), "Moulay Brahim": (31.29, -7.97, "مولاي إبراهيم"),
            "Asni": (31.25, -7.98, "أسني"), "Ouirgane": (31.17, -8.08, "ويرگان")},
    sites=[("Marrakech Field Hospital", "المستشفى الميداني بمراكش", 31.63, -8.01, "hospital"), ("Amizmiz Tent Camp", "مخيم أمزميز", 31.22, -8.24, "shelter"),
           ("Asni Health Center", "المركز الصحي أسني", 31.25, -7.98, "hospital"), ("Ibn Tofail Hospital Marrakech", "مستشفى ابن طفيل بمراكش", 31.64, -8.00, "hospital")],
)
C["PH"] = dict(
    scenario="Super typhoon and storm surge, Leyte (Philippines)", hazard="typhoon", start=datetime(2013, 11, 8, 4, 40), span_h=8, phone="+63", split="test",
    report_langs={"tl": .55, "en": .45}, shelter_langs={"en": .7, "tl": .3},
    spoken=[("Waray", .7), ("Tagalog", .6), ("Cebuano", .2), ("English", .4)],
    male=[N("Juan"), N("Jose"), N("Ramon"), N("Eduardo"), N("Rodolfo"), N("Ernesto"), N("Romeo")],
    female=[N("Maria Cristina", "Ma. Cristina"), N("Maria Luisa", "Ma. Luisa"), N("Josefina"), N("Rosario"), N("Teresita"), N("Ana"), N("Leonora")],
    family=[N("Dela Cruz", "De la Cruz", "dela Cruz"), N("Santos"), N("Reyes"), N("Bautista"), N("Garcia"), N("Mendoza"), N("Villanueva")],
    nicks=["Jun", "Bong", "Boy", "Tina", "Malou", "Charing", "Tess", "Inday"],
    places={"Tacloban": (11.24, 125.00, None), "Palo": (11.16, 124.99, None), "Tanauan": (11.11, 125.02, None), "Basey": (11.28, 125.07, None),
            "Ormoc": (11.01, 124.61, None)},
    sites=[("Eastern Visayas Medical Center", None, 11.23, 125.00, "hospital"), ("Tacloban Astrodome Evacuation Center", None, 11.24, 125.01, "shelter"),
           ("Palo Evacuation Center", None, 11.16, 124.99, "shelter"), ("Ormoc District Hospital", None, 11.01, 124.61, "hospital")],
)

# Local shelters and health posts in each affected town (more places to predict between)
LOCAL_SHELTER = {"PK": "Government School {p} Shelter", "NP": "{p} Community Shelter", "MX": "Albergue Escuela {p}", "BR": "Abrigo Escola {p}",
                 "IT": "Area di accoglienza {p}", "HT": "Abri Lekol {p}", "JP": "{p} Community Center Shelter", "TR": "{p} Cadirkent",
                 "MA": "{p} Tent Camp", "PH": "{p} Evacuation Center"}
LOCAL_CLINIC = {"PK": "{p} Basic Health Unit", "NP": "{p} Health Post", "MX": "Centro de Salud {p}", "BR": "Posto de Saude {p}",
                "IT": "Posto medico avanzato {p}", "HT": "Dispansè {p}", "JP": "{p} Clinic", "TR": "{p} Sahra Hastanesi",
                "MA": "{p} Health Center", "PH": "{p} Rural Health Unit"}
for _cc, _cfg in C.items():
    _names = {x[0] for x in _cfg["sites"]}
    for _i, (_pl, (_la, _lo, _nat)) in enumerate(_cfg["places"].items()):
        for _tpl, _kind, _use in ((LOCAL_SHELTER[_cc], "shelter", True), (LOCAL_CLINIC[_cc], "hospital", _i % 2 == 0)):
            _n = _tpl.format(p=_pl)
            if _use and _n not in _names and not any(_pl in x and _kind in y for x, y in [(z[0], z[4]) for z in _cfg["sites"]]):
                _cfg["sites"].append((_n, None, round(_la + .01, 4), round(_lo + .01, 4), _kind)); _names.add(_n)

# =============================================================================
# Helpers
# =============================================================================
def pick(x): return random.choice(x)
def wpick(d): return random.choices(list(d), weights=list(d.values()))[0]

def typo(s, p):
    if not s or random.random() > p or not s.isascii() or len(s) < 4:
        return s
    i = random.randint(1, len(s) - 2)
    k = random.choice(["drop", "double", "swap"])
    if k == "drop": return s[:i] + s[i + 1:]
    if k == "double": return s[:i] + s[i] + s[i:]
    return s[:i] + s[i + 1] + s[i] + s[i + 2:]

def jitter(lat, lon, km):
    d = km / 111.0
    return round(lat + random.uniform(-d, d), 5), round(lon + random.uniform(-d, d), 5)

import math
def km(a, b, c, d):
    r = math.radians
    h = math.sin(r(c - a) / 2) ** 2 + math.cos(r(a)) * math.cos(r(c)) * math.sin(r(d - b) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))

HAZ_SCALE = {"flood": 60, "flash flood": 40, "hurricane": 40, "earthquake": 25, "typhoon": 30}
def choose_site(p, cond, cfg):
    """Where a found person ends up. Nearer is likelier; injured people go to hospitals; children,
    elderly and people with limited mobility stay closer; flash floods carry people downstream;
    people drift toward their home town."""
    home = cfg["places"][p["home"]]
    slow = p["age"] < 12 or p["age"] >= 70 or 4 in p["marks"] or 7 in p["marks"]
    w = []
    for s in cfg["sites"]:
        d = km(p["lat"], p["lon"], s[2], s[3])
        wt = math.exp(-d / (HAZ_SCALE[cfg["hazard"]] * (0.35 if slow else 1.0)))
        if s[4] == "hospital":
            wt *= 6 if cond in ("injured", "critical", "unconscious", "deceased") else 5 if set(p["medical"]) & {0, 2, 4, 5} else 0.35
        else:
            wt *= 0.3 if cond in ("critical", "unconscious", "deceased") else 1.6
        if cfg["hazard"] == "flash flood" and s[2] < p["lat"] - 0.02:
            wt *= 2.0
        if km(home[0], home[1], s[2], s[3]) < 12:
            wt *= 1.6
        w.append(wt)
    return random.choices(cfg["sites"], weights=w)[0]

def noun_idx(gender, age):
    return (0 if gender == "M" else 1) + (2 if age < 14 else 0)

def article(age):
    return "an" if str(age).startswith("8") or age in (11, 18) else "a"

# =============================================================================
# People
# =============================================================================
def make_person(pid, cc):
    cfg = C[cc]
    p = {"person_id": pid, "country": cc}
    r = random.random()
    p["age"] = random.randint(1, 17) if r < .25 else random.randint(18, 59) if r < .78 else random.randint(60, 90)
    p["gender"] = pick(["M", "F"])
    given = pick(cfg["male"] if p["gender"] == "M" else cfg["female"])
    tokens = [given, pick(cfg["family"])]
    if cfg.get("double_surname") and random.random() < .7:
        second = pick([f for f in cfg["family"] if f is not tokens[1]])
        tokens.append(second)
    p["tokens"] = tokens
    p["japanese"] = cfg.get("japanese", False)
    p["nick"] = pick(cfg["nicks"]) if cfg["nicks"] and random.random() < .3 else ""
    p["languages"] = [l for l, pr in cfg["spoken"] if random.random() < pr] or [cfg["spoken"][0][0]]
    p["height"] = random.randint(80, 150) if p["age"] < 13 else random.randint(145, 185)
    p["clothing"] = [(random.randrange(len(COLORS)), i) for i in random.sample(range(len(ITEMS)), k=random.choice([1, 2]))]
    pool = [i for i, m in enumerate(MARKS) if not (m == "uses a walking stick" and p["age"] < 55)]
    p["marks"] = random.sample(pool, k=random.choice([0, 1, 1, 2]))
    med = []
    if p["age"] >= 65 and random.random() < .3: med.append(1)
    if p["age"] >= 40 and random.random() < .2: med.append(random.choice([0, 2]))
    if p["gender"] == "F" and 20 <= p["age"] <= 40 and random.random() < .07: med.append(4)
    if random.random() < .05: med.append(random.choice([3, 5]))
    p["medical"] = sorted(set(med))
    p["home"] = pick(list(cfg["places"]))
    lat, lon, _ = cfg["places"][p["home"]]
    p["last_seen_place"] = p["home"] if random.random() < .7 else pick(list(cfg["places"]))
    p["lat"], p["lon"] = jitter(*cfg["places"][p["last_seen_place"]][:2], 1.5)
    p["last_seen"] = cfg["start"] + timedelta(minutes=random.randint(0, cfg["span_h"] * 60))
    return p

def canonical(tokens, japanese=False):
    return " ".join(t[0][0] for t in tokens)

def native_full(p):
    toks = p["tokens"]
    if not all(t[1] for t in toks):
        return None
    if p["japanese"]:  # family name first, no space
        return toks[1][1] + toks[0][1]
    return " ".join(t[1] for t in toks)

def write_name(p, lang, use_native_p):
    """Returns (written_name, name_latin) for one report. name_latin = standard Latin spelling of what was written."""
    toks = p["tokens"]
    mode = random.random()
    # nickname only
    if p["nick"] and mode < .12:
        return p["nick"], p["nick"]
    # first name only
    if mode < .22 and not p["japanese"]:
        t = toks[0]
        if random.random() < use_native_p and t[1]:
            return t[1], t[0][0]
        return typo(pick(t[0]), .1), t[0][0]
    # drop second surname sometimes
    if len(toks) == 3 and random.random() < .4:
        toks = toks[:2]
    latin_std = " ".join(t[0][0] for t in toks)
    if p["japanese"]:
        given, fam = toks[0], toks[1]
        if random.random() < use_native_p:
            return (fam[1] + (" " if random.random() < .4 else "") + given[1]), f"{given[0][0]} {fam[0][0]}"
        g, f = pick(given[0]), pick(fam[0])
        if random.random() < .5:  # family-name-first, often uppercase
            return f"{f.upper() if random.random() < .6 else f} {g}", f"{given[0][0]} {fam[0][0]}"
        return f"{g} {f}", f"{given[0][0]} {fam[0][0]}"
    if random.random() < use_native_p and all(t[1] for t in toks):
        return " ".join(t[1] for t in toks), latin_std
    if random.random() < use_native_p:  # accented forms where they exist
        return " ".join(t[1] or pick(t[0]) for t in toks), latin_std
    w = " ".join(typo(pick(t[0]), .08) for t in toks)
    if random.random() < .08:
        w = w.lower()
    return w, latin_std

def place_text(cc, place, lang):
    nat = C[cc]["places"][place][2]
    if nat and (lang in SCRIPT_LANGS or (not any(ord(ch) > 0x2FF for ch in nat) and lang != "en")):
        return nat
    return place

def site_text(site, lang):
    name, nat = site[0], site[1]
    if nat and (lang in SCRIPT_LANGS or (not any(ord(ch) > 0x2FF for ch in nat) and lang != "en")):
        return nat
    return name

def native_p(lang, cc):
    if lang in SCRIPT_LANGS: return .85
    if lang in ("es", "pt", "fr", "it", "tr", "ht"): return .6
    if lang == "en" and cc in ("PK", "NP", "MA", "JP"): return .1
    return .2

def lname(lang, l):
    return LANGNAME_T.get(lang, {}).get(l, l)

def join_list(lang, items):
    return LIST_SEP.get(lang, ", ").join(items)

# =============================================================================
# Report text + target
# =============================================================================
def empty_target(kind):
    return {"report_type": kind, "name": None, "name_latin": None, "age_min": None, "age_max": None, "gender": None,
            "clothing": [], "marks": [], "medical": [], "languages": [], "place": None, "location_now": None}

def missing_text(p, lang):
    t, cc, tgt = T[lang], p["country"], empty_target("missing")
    nm, nl = write_name(p, lang, native_p(lang, cc))
    age = max(0, p["age"] + (random.randint(-4, 4) if p["age"] >= 60 else random.randint(-1, 1) if p["age"] < 13 else random.randint(-2, 2)))
    tgt.update(name=nm, name_latin=nl, age_min=age, age_max=age)
    if random.random() < .75:
        noun = NOUN[lang][noun_idx(p["gender"], age)]
        parts = [t["mig"].format(name=nm, age=age, noun=noun, art=article(age))]
        tgt["gender"] = p["gender"]
    else:
        parts = [t["mi"].format(name=nm, age=age)]
    body = []
    if random.random() < .9:
        body.append(t["seen"].format(place=place_text(cc, p["last_seen_place"], lang))); tgt["place"] = p["last_seen_place"]
    if random.random() < .85:
        cl = p["clothing"]
        body.append(t["wear"].format(c=join_list(lang, [garment(lang, c, i) for c, i in cl])))
        tgt["clothing"] = [f"{COLORS[c]} {ITEMS[i]}" for c, i in cl]
    ms = [m for m in p["marks"] if random.random() < .85]
    if ms:
        body.append(" ".join(t["mark"].format(m=MARK_T[lang][m]) for m in ms) if lang == "en" else t["mark"].format(m=join_list(lang, [MARK_T[lang][m] for m in ms])))
        tgt["marks"] = [MARKS[m] for m in ms]
    md = [m for m in p["medical"] if random.random() < .85]
    if md:
        body.append(t["med"].format(x=join_list(lang, [MED_T[lang][m] for m in md]))); tgt["medical"] = [MEDICAL[m] for m in md]
    if random.random() < .45:
        body.append(t["speak"].format(l=join_list(lang, [lname(lang, l) for l in p["languages"]]))); tgt["languages"] = list(p["languages"])
    random.shuffle(body)
    parts += body
    if random.random() < .4:
        parts.append(pick(t["fill"]))
    sep = "" if lang in ("ja",) else " "
    text = sep.join(parts)
    if lang not in SCRIPT_LANGS and random.random() < .1:
        text = text.rstrip(".") + " !!"
    return text, tgt

def found_text(p, lang, est_age, unidentified, site, public, hurt):
    t, cc, tgt = T[lang], p["country"], empty_target("found")
    noun = NOUN[lang][noun_idx(p["gender"], est_age)]
    parts = [t["fi"].format(noun=noun, age=est_age, art=article(est_age))]
    tgt.update(gender=p["gender"], age_min=max(0, est_age - (3 if est_age < 14 else 5)), age_max=est_age + (3 if est_age < 14 else 5))
    if unidentified:
        parts.append(t["fnoname"])
    else:
        nm, nl = write_name(p, lang, native_p(lang, cc))
        parts.append(t["fname"].format(name=nm)); tgt.update(name=nm, name_latin=nl)
    body = []
    if random.random() < .85:
        cl = p["clothing"]
        body.append(t["wear"].format(c=join_list(lang, [garment(lang, c, i) for c, i in cl])))
        tgt["clothing"] = [f"{COLORS[c]} {ITEMS[i]}" for c, i in cl]
    ms = [m for m in p["marks"] if random.random() < .7]
    if ms:
        body.append(" ".join(t["mark"].format(m=MARK_T[lang][m]) for m in ms) if lang == "en" else t["mark"].format(m=join_list(lang, [MARK_T[lang][m] for m in ms])))
        tgt["marks"] = [MARKS[m] for m in ms]
    md = [m for m in p["medical"] if random.random() < .5]
    if md:
        body.append(t["med"].format(x=join_list(lang, [MED_T[lang][m] for m in md]))); tgt["medical"] = [MEDICAL[m] for m in md]
    if not unidentified and random.random() < .5:
        sp = p["languages"] if random.random() < .5 else p["languages"][:1]
        body.append(t["speak"].format(l=join_list(lang, [lname(lang, l) for l in sp]))); tgt["languages"] = list(sp)
    if random.random() < .7:
        fp = p["last_seen_place"] if random.random() < .6 else pick(list(C[cc]["places"]))
        body.append(t["fplace"].format(place=place_text(cc, fp, lang))); tgt["place"] = fp
    if hurt:
        body.append(t["hurt"])
    random.shuffle(body)
    parts += body
    if site and random.random() < .8:
        parts.append(t["fnow"].format(s=site_text(site, lang))); tgt["location_now"] = site[0]
    sep = "" if lang == "ja" else " "
    return sep.join(parts), tgt

# =============================================================================
# Build
# =============================================================================
PER_COUNTRY = 700
SYSTEM = ("You read reports about missing or found people after a disaster. The report can be in any language or script. "
          "Return only JSON with exactly these keys: report_type, name, name_latin, age_min, age_max, gender, clothing, marks, medical, "
          "languages, place, location_now. Copy the name exactly as written into name, and give its standard Latin spelling in name_latin. "
          "Write clothing, marks, medical and languages in plain English. Use null or [] when the report does not say something. Never guess.")

def main():
    people, missing, found, gt, fams, members, llm = [], [], [], [], [], [], []
    pid = 0; mr = 0; fr = 0; fam_n = 0
    for cc, cfg in C.items():
        cp = []
        for _ in range(PER_COUNTRY):
            pid += 1
            p = make_person(f"P{pid:05d}", cc)
            p["category"] = random.choices(["both", "missing_only", "found_only"], weights=[55, 20, 25])[0]
            cp.append(p)
        # registered families (~40% of people), grouped by home town
        byhome = {}
        for p in cp:
            if random.random() < .4:
                byhome.setdefault(p["home"], []).append(p)
        for home, ps in byhome.items():
            random.shuffle(ps)
            while ps:
                k = random.choice([1, 2, 2, 3, 3, 4]); grp, ps = ps[:k], ps[k:]
                fam_n += 1; fid = f"RF-{cc}-{fam_n:04d}"
                contact = pick(cfg["male"] + cfg["female"])[0][0] + " " + pick(cfg["family"])[0][0]
                fams.append({"family_id": fid, "country": cc, "contact_name": contact,
                             "contact_phone": f"{cfg['phone']}-{random.randint(300, 999)}-{random.randint(1000000, 9999999)}", "home_place": home,
                             "registered_before_disaster": True})
                for g in grp:
                    g["family_id"] = fid
                    members.append({"family_id": fid, "person_id": g["person_id"], "full_name": canonical(g["tokens"]), "native_name": native_full(g) or "",
                                    "other_names": g["nick"], "age": g["age"], "gender": g["gender"], "languages": "; ".join(g["languages"]),
                                    "marks": "; ".join(MARKS[m] for m in g["marks"]), "medical": "; ".join(MEDICAL[m] for m in g["medical"]),
                                    "phone": "", "has_photo": random.random() < .6})
        for p in cp:
            if p["category"] in ("both", "missing_only"):
                for k in range(random.choices([1, 2, 3], weights=[72, 22, 6])[0]):
                    lang = wpick(cfg["report_langs"])
                    text, tgt = missing_text(p, lang)
                    mr += 1; rid = f"MR-{cc}-{mr:05d}"
                    when = p["last_seen"] + timedelta(minutes=random.randint(45, 60 * 48) + k * random.randint(20, 400))
                    reporter = pick(cfg["male"] + cfg["female"])[0][0] + " " + p["tokens"][1][0][0]
                    missing.append({"report_id": rid, "country": cc, "reported_at": when.isoformat(timespec="minutes"), "report_language": lang,
                                    "via_family_registration": bool(p.get("family_id")) and random.random() < .6, "family_id": p.get("family_id", ""),
                                    "reporter_name": reporter, "reporter_phone": f"{cfg['phone']}-{random.randint(300, 999)}-{random.randint(1000000, 9999999)}",
                                    "last_seen_lat": p["lat"], "last_seen_lon": p["lon"],
                                    "last_seen_time": p["last_seen"].isoformat(timespec="minutes"), "text": text})
                    gt.append({"record_id": rid, "person_id": p["person_id"]})
                    llm.append((rid, cc, lang, cfg["split"], text, tgt))
            if p["category"] in ("both", "found_only"):
                for k in range(1 + (random.random() < .05)):
                    public = random.random() < .3
                    when = p["last_seen"] + timedelta(minutes=random.randint(60, 60 * 24 * 5))
                    hrs = (when - p["last_seen"]).total_seconds() / 3600
                    # outcomes get worse with age, medical needs and time missing
                    f = 1 + 3.0 * (p["age"] >= 70) + 1.5 * (p["age"] < 5) + 2.5 * (1 in p["medical"]) + 2.0 * bool(set(p["medical"]) & {0, 2, 4}) + hrs / 24
                    cond = random.choices(["stable", "injured", "critical", "unconscious", "deceased"], weights=[70, 18, 4 * f, 3 * f, 2 * f])[0]
                    site = choose_site(p, cond, cfg) if (not public or random.random() < .5) else None
                    lang = wpick(cfg["report_langs"] if public else cfg["shelter_langs"])
                    unid = cond in ("unconscious", "deceased") and random.random() < .7 or p["age"] < 5 and random.random() < .6 \
                        or 1 in p["medical"] and random.random() < .5 or random.random() < .06
                    est = max(0, p["age"] + (random.randint(-8, 8) if p["age"] >= 60 else random.randint(-2, 2) if p["age"] < 13 else random.randint(-5, 5)))
                    text, tgt = found_text(p, lang, est, unid, site, public, cond == "injured")
                    fr += 1; fid = f"FR-{cc}-{fr:05d}"
                    loc = (site[2], site[3]) if site else jitter(*cfg["places"][pick(list(cfg["places"]))][:2], 3)
                    minor = est < 18
                    consent = "family_liaison_only" if cond == "deceased" else "child_protection_only" if minor else \
                        "pending" if (unid or cond in ("unconscious", "critical")) else \
                        random.choices(["share_location", "message_only", "no_contact"], weights=[72, 20, 8])[0]
                    found.append({"found_id": fid, "country": cc, "found_at": when.isoformat(timespec="minutes"), "report_language": lang,
                                  "source": "public" if public else site[4], "site": site[0] if site else "",
                                  "reporter_phone": f"{cfg['phone']}-{random.randint(300, 999)}-{random.randint(1000000, 9999999)}",
                                  "found_lat": round(loc[0], 5), "found_lon": round(loc[1], 5), "condition": cond, "consent": consent,
                                  "is_minor_estimate": minor, "text": text})
                    gt.append({"record_id": fid, "person_id": p["person_id"]})
                    llm.append((fid, cc, lang, cfg["split"], text, tgt))
        people += cp

    # ---------------- write CSVs ----------------
    def wcsv(name, rows):
        with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    missing.sort(key=lambda r: (r["country"], r["reported_at"])); found.sort(key=lambda r: (r["country"], r["found_at"]))
    wcsv("missing_reports.csv", missing); wcsv("found_reports.csv", found); wcsv("ground_truth.csv", gt)
    wcsv("families.csv", fams); wcsv("family_members.csv", members)
    wcsv("people.csv", [{"person_id": p["person_id"], "country": p["country"], "scenario": C[p["country"]]["scenario"], "category": p["category"],
                         "canonical_name": canonical(p["tokens"]), "native_name": native_full(p) or "", "nickname": p["nick"], "gender": p["gender"], "age": p["age"],
                         "languages": "; ".join(p["languages"]), "clothing": "; ".join(f"{COLORS[c]} {ITEMS[i]}" for c, i in p["clothing"]),
                         "marks": "; ".join(MARKS[m] for m in p["marks"]), "medical": "; ".join(MEDICAL[m] for m in p["medical"]),
                         "home_place": p["home"], "last_seen_place": p["last_seen_place"], "last_seen_time": p["last_seen"].isoformat(timespec="minutes"),
                         "family_id": p.get("family_id", "")} for p in people])

    # ---------------- LLM fine-tuning files (split by country) ----------------
    random.shuffle(llm)
    splits = {"train": [], "val": [], "test": []}
    for rid, cc, lang, sp, text, tgt in llm:
        s = "test" if sp == "test" else ("val" if random.random() < .1 else "train")
        splits[s].append({"id": rid, "country": cc, "language": lang, "input": text, "output": tgt,
                          "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text},
                                       {"role": "assistant", "content": json.dumps(tgt, ensure_ascii=False)}]})
    for s, rows in splits.items():
        with open(os.path.join(OUT, f"llm_{s}.jsonl"), "w", encoding="utf-8") as f:
            for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

    schema = {"type": "object", "additionalProperties": False, "properties": {
        "report_type": {"type": "string", "enum": ["missing", "found"]}, "name": {"type": ["string", "null"]}, "name_latin": {"type": ["string", "null"]},
        "age_min": {"type": ["integer", "null"]}, "age_max": {"type": ["integer", "null"]}, "gender": {"type": ["string", "null"], "enum": ["F", "M", None]},
        "clothing": {"type": "array", "items": {"type": "string"}}, "marks": {"type": "array", "items": {"type": "string"}},
        "medical": {"type": "array", "items": {"type": "string"}}, "languages": {"type": "array", "items": {"type": "string"}},
        "place": {"type": ["string", "null"]}, "location_now": {"type": ["string", "null"]}},
        "required": ["report_type", "name", "name_latin", "age_min", "age_max", "gender", "clothing", "marks", "medical", "languages", "place", "location_now"]}
    json.dump(schema, open(os.path.join(OUT, "schema.json"), "w"), indent=2)
    json.dump({"system_prompt": SYSTEM, "vocab": {"clothing_colors": COLORS, "clothing_items": ITEMS, "marks": MARKS, "medical": MEDICAL},
               "scenarios": {cc: {"scenario": c["scenario"], "hazard": c["hazard"], "split": c["split"], "start": c["start"].isoformat(),
                                  "places": {k: v[:2] for k, v in c["places"].items()},
                                  "sites": [{"name": s[0], "lat": s[2], "lon": s[3], "kind": s[4]} for s in c["sites"]]} for cc, c in C.items()}},
              open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"people {len(people)} | families {len(fams)} ({len(members)} members) | missing {len(missing)} | found {len(found)}")
    print({k: len(v) for k, v in splits.items()})

if __name__ == "__main__":
    main()
