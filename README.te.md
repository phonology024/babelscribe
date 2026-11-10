
# babelscribe — ఏ GPU పైనైనా ఉచితంగా, ఇంటర్నెట్ అవసరం లేకుండా Speech-to-Text మరియు Subtitles

## ఇప్పటికే ఉన్న ఇతర సాధనాలతో పోలిస్తే babelscribe ఎందుకు?

| | AMD / Intel GPU మద్దతు | Windows‌లో అదనపు Build అవసరం లేదు | వీడియో నుంచి Subtitles | పెద్ద ఫైళ్లలో పునరావృత సమస్య లేదు | మీ భాషకు మెరుగైన Text |
|---|---|---|---|---|---|
| **babelscribe** | ✅ Vulkan | ✅ `whisper-cli` ముందుగానే డౌన్‌లోడ్ అవుతుంది | ✅ ffmpeg అందుబాటులో ఉంటుంది | ✅ డిఫాల్ట్‌గా `--max-context 0` | ✅ Hybrid fine-tune text + turbo timing |
| whisper.cpp (raw) | ✅ Vulkan — మీరే Compile చేస్తే | ❌ అధికారిక Releases‌లో Windows Vulkan Build లేదు | ❌ 16 kHz WAV మాత్రమే | ⚠️ సరైన Flag మీకు తెలిసి ఉండాలి | ❌ |
| faster-whisper / WhisperX | ❌ GPU మద్దతు NVIDIA CUDAకే పరిమితం | ✅ pip | ✅ | ⚠️ | ⚠️ Manual setup అవసరం |
| Cloud APIs | n/a (Cloud) | ✅ | ✅ | ✅ | ❌ — మీ Audio కంప్యూటర్ బయటకు వెళ్తుంది; ప్రతి నిమిషానికి చార్జీలు ఉండవచ్చు |

babelscribe ఈ ప్రాజెక్టులను **భర్తీ చేయదు** — ఇది whisper.cpp ఆధారంగా పనిచేస్తుంది. అయితే, మీ GPU కోసం Compile చేయడం, Media Format మార్చడం, సరైన Device ఎంచుకోవడం, పెద్ద ఫైళ్లలో పునరావృత సమస్యను నివారించడం, అలాగే మీ భాషకు ప్రత్యేకంగా శిక్షణ పొందిన Fine-tune‌ను ఖచ్చితమైన Timestamps‌తో కలపడం వంటి క్లిష్టమైన పనులను సులభతరం చేస్తుంది.

## తరచుగా అడిగే ప్రశ్నలు (FAQ)

**Windows‌లో AMD GPU ఉపయోగించి Whisper‌ను ఎలా అమలు చేయాలి?**

`pip install babelscribe` అమలు చేసి, ఆ తర్వాత `babelscribe video.mp4` ఉపయోగించండి. ఇది Windows మరియు Linux‌లోని AMD Radeon (అలాగే Intel Arc / NVIDIA) GPUలపై పనిచేసే Vulkan Build of whisper.cpp‌ను డౌన్‌లోడ్ చేస్తుంది. ROCm, CUDA లేదా స్వయంగా Compile చేయాల్సిన అవసరం లేదు.

**వీడియో నుంచి ఉచితంగా, ఇంటర్నెట్ లేకుండా SRT Subtitles ఎలా తయారు చేయాలి?**

`babelscribe video.mp4 -f srt` అమలు చేస్తే, వీడియో ఉన్న అదే Folder‌లో `video.srt` ఫైల్ రూపొందుతుంది. మీ ఫైల్ ఎక్కడికీ Upload కాదు; మొత్తం ప్రక్రియ మీ కంప్యూటర్‌లోనే జరుగుతుంది.

**Thai భాష కోసం అత్యంత ఖచ్చితమైన ఉచిత Transcription ఏది?**

`babelscribe video.mp4 -l th --accurate` ఉపయోగించండి. ఇది Text కోసం Pathumma Whisper (NECTEC), Timing కోసం Whisper turbo ఉపయోగిస్తుంది. Google FLEURS Benchmark‌లో దీని CER 8.9% కాగా, సాధారణ Whisper turbo కోసం 15.9%. Thonburian Whisper కూడా అందుబాటులో ఉంది (`--text-model thai-thonburian`).

**నా కంప్యూటర్‌లోని వీడియోను Claude / ChatGPT Codex / Gemini ద్వారా Transcribe చేయవచ్చా?**

అవును! babelscribe‌ను MCP Server‌గా జోడించండి (*Use it from an AI app* విభాగాన్ని చూడండి). Claude Desktop‌లో `babelscribe.mcpb` ఫైల్‌ను ఒక్కసారి Click చేయడం ద్వారా Install చేయవచ్చు. ఆ తర్వాత AI App మీ కంప్యూటర్‌లోని ఫైల్‌ను గుర్తించి, మీ GPU ఉపయోగించి Transcribe చేయగలదు. అలాగే Text‌ను Proofread చేయడం, Translate చేయడం లేదా Summarise చేయడం కూడా చేయగలదు.

**ఇది ఎంత వేగంగా పనిచేస్తుంది?**

AMD Radeon RX 9070 XT GPUపై Whisper large-v3-turbo ఉపయోగించినప్పుడు, ఇది Real-time కంటే సుమారు 20 రెట్లు వేగంగా పనిచేస్తుంది. ఉదాహరణకు, 19 నిమిషాల Talk‌ను 48 సెకన్లలో Transcribe చేయగలదు.

**ఏయే భాషలకు మద్దతు ఉంది?**

Whisper మద్దతు ఇచ్చే మొత్తం 99 భాషలకు మద్దతు ఉంది. భాషను స్వయంచాలకంగా గుర్తించే సదుపాయం కూడా ఉంది. వాటిలో 16 భాషల Benchmark Error Rates‌ను FLEURS పట్టికలో చూడవచ్చు.

**faster-whisper లేదా WhisperX కంటే ఇది మెరుగైనదా?**

ఈ రెండూ NVIDIA GPUలపై అద్భుతంగా పనిచేస్తాయి. కానీ AMD / Intel GPUలపై ఇవి CPUకు మారతాయి. babelscribe ప్రత్యేకత ఏ GPU అయినా ఉపయోగించగలగడం, Zero Setup, అలాగే Community Fine-tunes ద్వారా మెరుగైన Thai / Hindi ఫలితాలను అందించడం. మీ దగ్గర NVIDIA GPU ఉండి, Python‌తో పనిచేయడం ఇష్టమైతే faster-whisper కూడా మంచి ఎంపిక.

## ఉపయోగించే విధానం (Usage)

క్రింది Commands ద్వారా Audio లేదా Video ఫైళ్లను Transcribe చేసి, వివిధ Formats‌లో Subtitles పొందవచ్చు.

```bash
babelscribe talk.mp4 -f srt,vtt,txt,json          # all formats
babelscribe reel.mp4 -f ass                        # karaoke subtitles, one highlight per word
babelscribe podcast.mp3 -l en -m large-v3          # pick language and model
babelscribe talk.mp4 -l hi --accurate              # slower, fewest errors (best model per language)
babelscribe vo.wav -l th --text-model thai-thonburian   # hybrid: pick a Thai fine-tune yourself
babelscribe talk.mp4 --prompt "Pitakpong, babelscribe"   # bias the spelling of names and terms
babelscribe talk.mp4 --translate                   # subtitles translated to English
babelscribe devices                                # GPUs whisper.cpp can see
babelscribe models                                 # models and fine-tunes
babelscribe talk.mp4 --bin /path/to/whisper-cli    # use your own whisper.cpp build
```

### Python ద్వారా ఉపయోగించడం

మీ Python ప్రాజెక్ట్‌లో కూడా babelscribe‌ను ఉపయోగించవచ్చు:

```python
from babelscribe.api import transcribe_file
r = transcribe_file("talk.mp4", lang="auto", formats=["srt", "txt"])   # or accurate=True, prompt="names, terms"
print(r["lang"], r["device"], r["files"]); print(r["text"][:200])
```

### Models మరియు అదనపు భాషా మద్దతు

Models మొదటిసారి ఉపయోగించినప్పుడు `~/.babelscribe/models` అనే Folder‌లో Download అవుతాయి. ఈ Location‌ను మార్చడానికి `BABELSCRIBE_MODELS` ఉపయోగించవచ్చు.

Hybrid Fine-tunes వాటి అసలు Hugging Face Repository నుంచి మీ కంప్యూటర్‌లోనే Convert అవుతాయి. ఇందుకోసం ఒక్కసారి `pip install "babelscribe[finetune]"` Install చేయాలి.

Converted Model Weights‌ను మళ్లీ పంపిణీ చేయరు. అందువల్ల ప్రతి Fine-tune దాని స్వంత Licence నిబంధనలను కొనసాగిస్తుంది.

Thai భాషలో Word Boundaries కోసం `pip install "babelscribe[thai]"` Install చేయండి.

## హార్డ్‌వేర్ మరియు GPU మద్దతు

| మీ హార్డ్‌వేర్ | ఉపయోగించే Backend | ముందుగానే సిద్ధం చేసిన Asset |
|---|---|---|
| Windows‌లో AMD / NVIDIA / Intel GPU | Vulkan | `windows-x64-vulkan` |
| Windows‌లో NVIDIA | Vulkan (అదే Build) | `windows-x64-vulkan` |
| Linux‌లో NVIDIA (ప్రత్యామ్నాయం) | CUDA | `linux-x64-cuda` (`--flavor cuda`) |
| Linux‌లో AMD / NVIDIA / Intel GPU | Vulkan | `linux-x64-vulkan` |
| Apple Silicon | Metal | `macos-arm64-metal` |
| ఉపయోగించగల GPU లేనప్పుడు | CPU | `*-cpu` (`--flavor cpu`) |
