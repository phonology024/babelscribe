"""Build the SEO guide pages in docs/ from the PAGES table below: python docs/tools/build_pages.py"""
import html
import json
from pathlib import Path

BASE = "https://phonology024.github.io/babelscribe/"
DOCS = Path(__file__).resolve().parents[1]

CSS = """:root{--bg:#f7f8fb;--fg:#141a2b;--mut:#5a6378;--line:#e3e6ee;--acc:#0b7fc7;--code:#eef2f8}
@media (prefers-color-scheme:dark){:root{--bg:#0f1422;--fg:#e8ecf5;--mut:#9aa4bb;--line:#263049;--acc:#5ac8ff;--code:#1d2640}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 system-ui,-apple-system,"Segoe UI","Noto Sans Thai",sans-serif}
main{max-width:780px;margin:0 auto;padding:36px 16px 64px}a{color:var(--acc)}h1{font-size:1.75rem;line-height:1.25}h2{margin-top:2em;font-size:1.25rem}
.lead{color:var(--mut);font-size:1.08rem}pre{background:var(--code);padding:14px 16px;border-radius:10px;overflow-x:auto;font-size:.9rem}
code{font-family:ui-monospace,Consolas,monospace}p code,li code,td code{background:var(--code);padding:1px 5px;border-radius:5px}
table{border-collapse:collapse;width:100%;font-size:.95rem}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left}
.nav{font-size:.95rem}.foot{color:var(--mut);margin-top:3em;font-size:.9rem}"""


def page(slug, lang, title, desc, h1, lead, body, faq):
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "TechArticle", "headline": h1, "description": desc, "inLanguage": lang, "url": BASE + slug,
         "author": {"@type": "Person", "name": "phonology024"}, "dateModified": "2026-10-06",
         "about": {"@type": "SoftwareApplication", "name": "babelscribe", "url": BASE}},
        {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q,
                                            "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]}
    faq_html = "".join(f"<h3>{html.escape(q)}</h3><p>{html.escape(a)}</p>" for q, a in faq)
    faq_title = "คำถามที่พบบ่อย" if lang == "th" else "FAQ"
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{BASE}{slug}"><link rel="icon" href="icon.png">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{BASE}{slug}"><meta property="og:image" content="{BASE}icon.png">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script><style>{CSS}</style></head>
<body><main><p class="nav"><a href="./">babelscribe</a> · <a href="https://github.com/phonology024/babelscribe">GitHub</a></p>
<h1>{html.escape(h1)}</h1><p class="lead">{lead}</p>{body}<h2>{faq_title}</h2>{faq_html}
<p class="foot">babelscribe is free and open source (MIT) · <a href="privacy.html">Privacy</a></p></main></body></html>"""


PAGES = [
    ("whisper-amd-gpu-windows.html", "en",
     "How to run Whisper on an AMD GPU on Windows (no ROCm, no CUDA) — babelscribe",
     "Run OpenAI Whisper speech-to-text on an AMD Radeon GPU on Windows in two commands. Vulkan build of whisper.cpp, "
     "no ROCm, no CUDA, no compiling.",
     "How to run Whisper on an AMD Radeon GPU on Windows",
     "Short answer: <code>pip install babelscribe</code>, then <code>babelscribe video.mp4</code>. It downloads a Vulkan "
     "build of whisper.cpp that runs on Radeon cards — no ROCm, no CUDA, no Visual Studio.",
     """<h2>Why Whisper is hard on AMD + Windows</h2>
<p>Most Whisper tools (openai-whisper, faster-whisper, WhisperX) use PyTorch or CTranslate2 with CUDA, so on a Radeon card they fall back to the CPU. ROCm on Windows covers only some cards and some libraries. whisper.cpp does run on AMD through <b>Vulkan</b>, but its official releases ship no Windows Vulkan binary, so you would normally install the Vulkan SDK and Visual Studio and compile it yourself.</p>
<h2>Two-command setup</h2>
<pre><code>pip install babelscribe
babelscribe "my video.mp4"            # writes my video.srt and my video.json
babelscribe devices                   # shows which GPUs Vulkan sees</code></pre>
<p>On first run babelscribe downloads a prebuilt <code>whisper-cli</code> (Vulkan, AVX2-compatible) and the <code>large-v3-turbo</code> model (~1.6 GB), then picks your discrete Radeon over the integrated GPU automatically. Use <code>--device N</code> to choose another card.</p>
<h2>How fast is it?</h2>
<table><tr><th>GPU</th><th>Audio</th><th>Time</th><th>Speed</th></tr><tr><td>AMD Radeon RX 9070 XT (Vulkan)</td><td>19.3 min TED talk</td><td>48 s</td><td>~24x real time</td></tr></table>
<p>Accuracy on that talk: 1.5% word error rate against the human captions. Use <code>--accurate</code> (large-v3 with beam search) when you want fewer errors and can wait about twice as long.</p>
<h2>Other formats and languages</h2>
<pre><code>babelscribe talk.mp4 -f srt,vtt,txt,json   # all outputs
babelscribe talk.mp4 -l ja                 # force Japanese (default: auto-detect)
babelscribe talk.mp4 --accurate            # fewest errors</code></pre>""",
     [("Does Whisper work on AMD GPUs?",
       "Yes. whisper.cpp runs on AMD Radeon GPUs through Vulkan on Windows and Linux. babelscribe downloads a prebuilt "
       "Vulkan build so you don't have to compile it."),
      ("Do I need ROCm to run Whisper on a Radeon card?",
       "No. The Vulkan backend works with the normal AMD Adrenalin driver; ROCm is not needed."),
      ("Which AMD cards are supported?",
       "Any card with a Vulkan 1.2+ driver should work; it has been tested on an RX 9070 XT. Reports for other cards are "
       "welcome on GitHub."),
      ("Can I use it without the command line?",
       "Yes: add babelscribe to Claude Desktop, Claude Code, Codex, Gemini CLI or Cursor as an MCP server and ask for "
       "subtitles in chat.")]),
    ("thai-speech-to-text.html", "th",
     "ถอดเสียงภาษาไทยเป็นข้อความและทำซับไทยฟรี แม่นยำ ใช้การ์ดจอในเครื่อง — babelscribe",
     "ถอดเสียงภาษาไทยจากวิดีโอหรือไฟล์เสียงเป็นข้อความและซับ SRT ฟรี ไม่ต้องอัปโหลด ใช้การ์ดจอ AMD NVIDIA Intel หรือ Mac "
     "แม่นกว่า Whisper ปกติเกือบเท่าตัวด้วย Pathumma Whisper",
     "ถอดเสียงภาษาไทยเป็นข้อความ ฟรี แม่นยำ ทำงานในเครื่อง",
     "คำตอบสั้นๆ: <code>pip install babelscribe</code> แล้วสั่ง <code>babelscribe คลิป.mp4 -l th --accurate</code> "
     "จะได้ไฟล์ซับ <code>.srt</code> ภาษาไทยข้างไฟล์วิดีโอ ไม่มีการอัปโหลดไฟล์ไปไหน",
     """<h2>แม่นแค่ไหน</h2>
<p>วัดบนชุดทดสอบ FLEURS ของ Google (ภาษาไทย 50 ประโยค) ด้วยอัตราความผิดพลาดระดับตัวอักษร (CER) ยิ่งน้อยยิ่งดี</p>
<table><tr><th>โมเดล</th><th>CER</th></tr>
<tr><td>Whisper large-v3-turbo (ค่าเริ่มต้น)</td><td>15.9%</td></tr>
<tr><td>Whisper large-v3</td><td>11.5%</td></tr>
<tr><td>Typhoon Whisper</td><td>11.9%</td></tr>
<tr><td>Thonburian Whisper (<code>--text-model thai-thonburian</code>)</td><td>9.1%</td></tr>
<tr><td><b>Pathumma Whisper ของ NECTEC (<code>--accurate</code>)</b></td><td><b>8.9%</b></td></tr></table>
<p>กับคลิป TEDxBangkok ยาว 14 นาทีที่พูดเร็วและมีศัพท์วัยรุ่น ความผิดพลาดลดจาก 22.7% เหลือ 16.4%</p>
<h2>ทำไมแม่นขึ้น</h2>
<p>โมเดลที่ฝึกเฉพาะภาษาไทยสะกดคำไทยได้ดีกว่ามาก แต่มักบอกเวลาของแต่ละช่วงไม่ได้ babelscribe จึงใช้ <b>โหมดไฮบริด</b> คือเอาข้อความจาก Pathumma Whisper แล้วเอาเวลาจาก Whisper turbo มาจับคู่กันทีละตัวอักษร และตัดซับเฉพาะตรงรอยต่อคำ (ใช้ pythainlp) จะได้ไม่มีคำไทยขาดกลางคำ</p>
<h2>ใช้งาน</h2>
<pre><code>pip install babelscribe
babelscribe คลิป.mp4 -l th              # เร็ว
babelscribe คลิป.mp4 -l th --accurate   # แม่นที่สุด (ช้ากว่า)
babelscribe คลิป.mp4 -l th -f srt,txt   # ได้ทั้งซับและข้อความล้วน</code></pre>
<p>ไม่อยากพิมพ์คำสั่ง: ติดตั้ง babelscribe ใน Claude Desktop แล้วพิมพ์ในแชทว่า “ทำซับไทยให้คลิปล่าสุดในโฟลเดอร์ดาวน์โหลด” ได้เลย</p>""",
     [("ถอดเสียงภาษาไทยฟรีโปรแกรมไหนแม่นที่สุด",
       "จากการวัดบน FLEURS ของ Google การใช้ Pathumma Whisper ของ NECTEC ผ่าน babelscribe --accurate ได้ CER 8.9% "
       "เทียบกับ Whisper turbo ปกติที่ 15.9%"),
      ("ต้องมีการ์ดจอ NVIDIA ไหม",
       "ไม่ต้อง ใช้ได้กับการ์ด AMD Radeon, Intel Arc, NVIDIA และ Mac (Apple Silicon) หรือใช้ CPU ก็ได้แต่ช้ากว่า"),
      ("ไฟล์ถูกอัปโหลดไปที่ไหนไหม", "ไม่ ทุกอย่างทำงานในเครื่องของคุณเอง ดาวน์โหลดแค่โปรแกรมและโมเดลครั้งแรก"),
      ("ทำซับไทยให้คลิป YouTube หรือ TikTok ได้ไหม",
       "ได้ ถ้ามีไฟล์วิดีโอในเครื่อง babelscribe จะสร้างไฟล์ .srt ที่นำไปอัปโหลดเป็นคำบรรยายได้ทันที")]),
    ("free-offline-subtitles.html", "en",
     "Generate SRT subtitles from a video for free, offline, in 99 languages — babelscribe",
     "Create SRT or VTT subtitles from any video or audio file for free and offline with Whisper on your own GPU "
     "(AMD, NVIDIA, Intel, Apple). No upload, no account.",
     "Generate SRT subtitles from a video — free and offline",
     "Short answer: <code>pip install babelscribe</code>, then <code>babelscribe video.mp4 -f srt</code>. You get "
     "<code>video.srt</code> next to the video, made on your own computer.",
     """<h2>Steps</h2>
<pre><code>pip install babelscribe              # Python 3.9+, Windows / Linux / macOS
babelscribe lecture.mp4 -f srt       # -> lecture.srt (language auto-detected)
babelscribe lecture.mp4 -f srt,vtt   # also WebVTT for web players
babelscribe lecture.mp4 --accurate   # fewer errors, slower</code></pre>
<p>Any format ffmpeg reads works as input: mp4, mkv, mov, webm, mp3, wav, m4a and more (ffmpeg is bundled). Long recordings are safe: babelscribe disables Whisper's context carry-over, which prevents the classic “same sentence repeated forever” bug on long files.</p>
<h2>Why offline</h2>
<p>Online subtitle generators upload your video, often limit length, and charge per minute. babelscribe runs OpenAI's Whisper model on your own GPU — AMD Radeon and Intel Arc via Vulkan, NVIDIA via Vulkan or CUDA, Apple Silicon via Metal — so private recordings never leave your machine and there are no limits.</p>
<h2>Accuracy</h2>
<p>On Google FLEURS, error rates with <code>--accurate</code> include English 5.7%, Spanish 4.2%, German 4.0%, Japanese 5.7% (CER) and Korean 3.9% (CER). The full 16-language table is in the <a href="https://github.com/phonology024/babelscribe#benchmark-16-languages-on-fleurs">README</a>.</p>""",
     [("How do I make subtitles for a video for free?",
       "Install babelscribe with pip and run babelscribe video.mp4 -f srt. It creates video.srt using Whisper on your own "
       "computer, free and without uploading the video."),
      ("Can I generate subtitles without uploading my video?",
       "Yes. babelscribe runs entirely offline after downloading the model once."),
      ("Which subtitle formats are supported?", "SRT, WebVTT, plain text and JSON with word timings."),
      ("Which languages can it subtitle?", "All 99 languages Whisper supports, with automatic language detection.")]),
]

if __name__ == "__main__":
    for slug, *rest in PAGES:
        (DOCS / slug).write_text(page(slug, *rest), encoding="utf-8")
    urls = [BASE, BASE + "privacy.html"] + [BASE + p[0] for p in PAGES]
    (DOCS / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>2026-10-06</lastmod></url>\n" for u in urls) + "</urlset>\n",
        encoding="utf-8")
    print("built", len(PAGES), "pages")
