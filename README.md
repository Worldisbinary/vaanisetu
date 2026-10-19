# VaaniSetu

Offline voice communication for low-bandwidth and disaster settings.
Team LITE, BITS Pilani - Smart India Hackathon 2026 (problem SIH26173 "iTantra").

**Status: v0.1 - packet / codec / transport core.** On-device STT/TTS and an Android app are on the roadmap. Nothing here records or synthesizes audio yet; the speech layer is an adapter interface with a text-only fallback and an optional Vosk STT backend.

## Problem

When networks are down or links are tiny (Wi-Fi Direct, Bluetooth, LoRa, a satellite transponder), sending voice is impractical. VaaniSetu turns speech into text on the device, squeezes the text into a very small packet, sends it over whatever low-bitrate link exists, and the receiver speaks it aloud with offline TTS. Target: 10 Indian languages (plus English) on 2 GB RAM phones, with packets around 40 bytes.

## How it works

```mermaid
flowchart LR
    A[Speech] -->|offline STT| B[Text]
    B -->|NFC + per-script 1-byte codec + deflate w/ preset dictionary| C[Compressed bytes]
    C -->|fragment + header + CRC-16| D[Packets]
    D -->|Wi-Fi Direct / BT / LoRa / satellite| E[Packets]
    E -->|reassemble, verify CRC| F[Text]
    F -->|offline TTS| G[Speech]
```

Codec: text is NFC-normalized, then each character of the language's script maps to 1 byte (Unicode block offset; Urdu uses a table), ASCII costs 1 byte, anything else is escaped. The result is also deflated with a preset dictionary of bundled emergency phrases; whichever is smaller is sent. Round-trip is exact (up to NFC).

## Packet layout (6 bytes overhead)

| Offset | Size | Field |
|---|---|---|
| 0 | 1 byte | version (3 bits) / codec method (1 bit) / language id (4 bits) |
| 1 | 1 byte | message id |
| 2 | 1 byte | fragment index (4 bits) / fragment count - 1 (4 bits) |
| 3 | 1 byte | payload length |
| 4 | n | payload |
| 4+n | 2 bytes | CRC-16/CCITT-FALSE over everything before it |

Languages: en, hi, bn, te, mr, ta, ur, gu, kn, ml, pa. Messages longer than the MTU are fragmented (up to 16 fragments) and reassembled in any order; duplicates are ignored. There is no ACK/retransmit protocol yet; the lossy-link test uses blind repetition.

## Real bench output

`vaanisetu bench` (packet bytes = full packet incl. 6-byte header+CRC, single packet). "dict" sentences are the bundled phrases that seed the compression dictionary, so they are the best case. "held-out" sentences are not in the dictionary and are the realistic case.

```text
lang set        UTF-8 B  packet B  ratio  text
en   dict             9        11  0.82x  Send help
en   dict            13        10  1.30x  We need water
en   dict            12        10  1.20x  I am injured
en   dict            22        10  2.20x  Need food and medicine
en   dict            28        10  2.80x  We are trapped, come quickly
en   dict             9         9  1.00x  Fire here
en   held-out        45        46  0.98x  Please send a doctor, many people are injured
en   held-out        33        38  0.87x  The water is rising, bring a boat
hi   dict            22        11  2.00x  मदद भेजो
hi   dict            41        10  4.10x  हमें पानी चाहिए
hi   dict            32        10  3.20x  मैं घायल हूँ
hi   dict            48        10  4.80x  खाना और दवाई चाहिए
hi   dict            53        10  5.30x  हम फंसे हैं, जल्दी आओ
hi   dict            36        10  3.60x  यहाँ आग लगी है
hi   held-out        88        34  2.59x  कृपया डॉक्टर भेजो, कई लोग घायल हैं
hi   held-out        60        28  2.14x  पानी बढ़ रहा है, नाव लाओ
bn   dict            37        11  3.36x  সাহায্য পাঠান
bn   dict            41        10  4.10x  আমাদের জল দরকার
bn   dict            19        10  1.90x  আমি আহত
bn   dict            48        10  4.80x  খাবার ও ওষুধ দরকার
bn   dict            80        10  8.00x  আমরা আটকে আছি, তাড়াতাড়ি আসুন
bn   dict            47        10  4.70x  এখানে আগুন লেগেছে
bn   held-out       100        41  2.44x  দয়া করে ডাক্তার পাঠান, অনেক মানুষ আহত
bn   held-out        52        25  2.08x  জল বাড়ছে, নৌকা আনুন
te   dict            34        11  3.09x  సహాయం పంపండి
te   dict            44        10  4.40x  మాకు నీరు కావాలి
te   dict            43        10  4.30x  నేను గాయపడ్డాను
te   dict            69        10  6.90x  ఆహారం మరియు మందులు కావాలి
te   dict            88        10  8.80x  మేము చిక్కుకున్నాము, త్వరగా రండి
te   dict            53        10  5.30x  ఇక్కడ మంటలు ఉన్నాయి
te   held-out       126        44  2.86x  దయచేసి డాక్టర్‌ను పంపండి, చాలా మంది గాయపడ్డారు
te   held-out        88        34  2.59x  నీరు పెరుగుతోంది, పడవ తీసుకురండి
mr   dict            25        11  2.27x  मदत पाठवा
mr   dict            54        10  5.40x  आम्हाला पाणी हवे आहे
mr   dict            29        10  2.90x  मी जखमी आहे
mr   dict            52        10  5.20x  अन्न आणि औषध हवे आहे
mr   dict            65        10  6.50x  आम्ही अडकलो आहोत, लवकर या
mr   dict            42        10  4.20x  इथे आग लागली आहे
mr   held-out       100        34  2.94x  कृपया डॉक्टर पाठवा, अनेक लोक जखमी आहेत
mr   held-out        56        24  2.33x  पाणी वाढत आहे, बोट आणा
ta   dict            49        11  4.45x  உதவி அனுப்புங்கள்
ta   dict            77        10  7.70x  எங்களுக்கு தண்ணீர் வேண்டும்
ta   dict            49        10  4.90x  நான் காயமடைந்தேன்
ta   dict            71        10  7.10x  உணவும் மருந்தும் வேண்டும்
ta   dict           127        10 12.70x  நாங்கள் சிக்கிக்கொண்டோம், சீக்கிரம் வாருங்கள்
ta   dict            62        10  6.20x  இங்கே தீ பிடித்துள்ளது
ta   held-out       161        39  4.13x  தயவுசெய்து மருத்துவரை அனுப்புங்கள், பலர் காயமடைந்துள்ளனர்
ta   held-out       110        30  3.67x  தண்ணீர் உயர்கிறது, படகு கொண்டு வாருங்கள்
ur   dict            19        11  1.73x  مدد بھیجیں
ur   dict            28        10  2.80x  ہمیں پانی چاہیے
ur   dict            22        10  2.20x  میں زخمی ہوں
ur   dict            35        10  3.50x  کھانا اور دوا چاہیے
ur   dict            51        10  5.10x  ہم پھنسے ہوئے ہیں، جلدی آئیں
ur   dict            25        10  2.50x  یہاں آگ لگی ہے
ur   held-out        71        37  1.92x  براہ کرم ڈاکٹر بھیجیں، کئی لوگ زخمی ہیں
ur   held-out        49        31  1.58x  پانی بڑھ رہا ہے، کشتی لائیں
gu   dict            25        11  2.27x  મદદ મોકલો
gu   dict            45        10  4.50x  અમને પાણી જોઈએ છે
gu   dict            32        10  3.20x  હું ઘાયલ છું
gu   dict            55        10  5.50x  ખોરાક અને દવા જોઈએ છે
gu   dict            62        10  6.20x  અમે ફસાયા છીએ, જલ્દી આવો
gu   dict            39        10  3.90x  અહીં આગ લાગી છે
gu   held-out       107        40  2.67x  કૃપા કરીને ડૉક્ટર મોકલો, ઘણા લોકો ઘાયલ છે
gu   held-out        75        32  2.34x  પાણી વધી રહ્યું છે, હોડી લાવો
kn   dict            34        11  3.09x  ಸಹಾಯ ಕಳುಹಿಸಿ
kn   dict            38        10  3.80x  ನಮಗೆ ನೀರು ಬೇಕು
kn   dict            55        10  5.50x  ನಾನು ಗಾಯಗೊಂಡಿದ್ದೇನೆ
kn   dict            51        10  5.10x  ಆಹಾರ ಮತ್ತು ಔಷಧ ಬೇಕು
kn   dict           103        10 10.30x  ನಾವು ಸಿಕ್ಕಿಹಾಕಿಕೊಂಡಿದ್ದೇವೆ, ಬೇಗ ಬನ್ನಿ
kn   dict            53        10  5.30x  ಇಲ್ಲಿ ಬೆಂಕಿ ಹತ್ತಿದೆ
kn   held-out       147        44  3.34x  ದಯವಿಟ್ಟು ವೈದ್ಯರನ್ನು ಕಳುಹಿಸಿ, ಅನೇಕ ಜನರು ಗಾಯಗೊಂಡಿದ್ದಾರೆ
kn   held-out        70        25  2.80x  ನೀರು ಏರುತ್ತಿದೆ, ದೋಣಿ ತನ್ನಿ
ml   dict            40        11  3.64x  സഹായം അയയ്ക്കൂ
ml   dict            59        10  5.90x  ഞങ്ങൾക്ക് വെള്ളം വേണം
ml   dict            43        10  4.30x  ഞാൻ പരിക്കേറ്റു
ml   dict            62        10  6.20x  ഭക്ഷണവും മരുന്നും വേണം
ml   dict            64        10  6.40x  ഞങ്ങൾ കുടുങ്ങി, വേഗം വരൂ
ml   dict            46        10  4.60x  ഇവിടെ തീപിടിച്ചു
ml   held-out       141        41  3.44x  ദയവായി ഡോക്ടറെ അയയ്ക്കൂ, നിരവധി പേർക്ക് പരിക്കേറ്റു
ml   held-out        91        32  2.84x  വെള്ളം ഉയരുന്നു, ബോട്ട് കൊണ്ടുവരൂ
pa   dict            22        11  2.00x  ਮਦਦ ਭੇਜੋ
pa   dict            54        10  5.40x  ਸਾਨੂੰ ਪਾਣੀ ਚਾਹੀਦਾ ਹੈ
pa   dict            35        10  3.50x  ਮੈਂ ਜ਼ਖਮੀ ਹਾਂ
pa   dict            61        10  6.10x  ਖਾਣਾ ਅਤੇ ਦਵਾਈ ਚਾਹੀਦੀ ਹੈ
pa   dict            63        10  6.30x  ਅਸੀਂ ਫਸੇ ਹੋਏ ਹਾਂ, ਜਲਦੀ ਆਓ
pa   dict            42        10  4.20x  ਇੱਥੇ ਅੱਗ ਲੱਗੀ ਹੈ
pa   held-out        98        38  2.58x  ਕਿਰਪਾ ਕਰਕੇ ਡਾਕਟਰ ਭੇਜੋ, ਕਈ ਲੋਕ ਜ਼ਖਮੀ ਹਨ
pa   held-out        72        31  2.32x  ਪਾਣੀ ਵਧ ਰਿਹਾ ਹੈ, ਕਿਸ਼ਤੀ ਲਿਆਓ

dict      n=66  packet bytes min/median/max = 9/10/11; <=40 B: 66/66
held-out  n=22  packet bytes min/median/max = 24/34/46; <=40 B: 17/22
all       n=88  packet bytes min/median/max = 9/10/46; <=40 B: 83/88
(packet bytes include the 6-byte header+CRC; 'dict' phrases seed the compression dictionary, 'held-out' do not)
```

Honest reading: the ~40-byte target is met for every dictionary phrase (9-11 bytes) but only for part of the held-out sentences; the longer ones exceed it (see table). English gains nothing from the codec on held-out text (ratio below 1.0x, because the 6-byte overhead outweighs ASCII-level savings). Translations are hand-written for the prototype and need native-speaker review. Sizes are for text only, measured, not estimates for audio.

## Run

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q && ruff check .
vaanisetu bench
vaanisetu receive --count 1 &                  # terminal 1
vaanisetu send "मदद भेजो" --lang hi            # terminal 2 (UDP, 127.0.0.1:47474)
```

Optional STT: `pip install -e ".[vosk]"` and pass a model directory to `vaanisetu.speech.VoskSTT`.

## Roadmap

On-device STT/TTS, Android app, ACK/retransmit and forward error correction, real LoRa/Bluetooth transports, native-speaker-reviewed phrase sets.

## License

MIT (c) 2026 Aman Arora
