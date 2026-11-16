
PART A : 

Voice Agents 101: The Architecture Behind AI That Talks Back

The first time I built a voice agent and got on a call with it, the thing felt like talking to someone over a satellite phone in 2003. Long pauses, unnatural cadence, occasional cuts where it would just keep talking over me. The text version of the same product was usable. The voice version was not. That was the moment I learned that text engineering and voice engineering are not the same craft.

The moment you introduce audio, you are dealing with a fundamentally different latency profile, a different failure mode surface, and a different set of tradeoffs than anything you would encounter in a text-based system. Voice agents aren’t just LLMs with a speaker attached. They are pipelines, and every stage of that pipeline fights against the same constraint: time.

This post covers how the voice agent pipeline actually works, the architectural choice between cascade and end-to-end speech models, the latency budget you are working within, what full-duplex means and why it is hard, and the design decisions that determine whether your voice agent feels natural or robotic.

The Three-Stage Pipeline
At its core, the most common voice agent architecture is built on three sequential stages.

Speech-to-Text (STT) takes the raw audio from the microphone and converts it into text that the LLM can process. The dominant options here are OpenAI Whisper (open-source, extremely accurate, but has latency), Deepgram (low-latency streaming transcription, production-proven), AssemblyAI (good accuracy, streaming support), and a handful of others. The key metric is not just word error rate but time to transcript — how long it takes to produce a transcript. A 98% accurate transcription that takes 800ms to produce is often worse than a 95% accurate one that takes 150ms.

LLM is the brain. It takes the transcript, applies context and memory, and generates a response. The same models you would use in text apply here, but the prompt structure changes: voice conversations are shorter-turn, more casual, and the model absolutely cannot produce markdown, numbered lists, or long walls of text. Every response needs to be spoken aloud naturally.

Text-to-Speech (TTS) converts the LLM’s text response to audio. The options range from older, robotic systems to modern neural TTS that sounds remarkably human: ElevenLabs, Cartesia (exceptionally low-latency), OpenAI TTS, PlayHT, and others. The metric that matters most in production is time to first audio chunk — how long before the user hears anything at all.

Stitching these three stages together is straightforward but making them feel seamless is not.

Cascade vs. End-to-End Speech Models
Before we get deeper into the cascade pipeline, you should know that there is now a second architectural family that didn’t really exist 18 months ago: end-to-end speech models.

Cascade is what we just described. STT transcribes audio to text, an LLM produces text, TTS turns that text back into audio. You get full control of every stage, complete observability, and the ability to swap components independently. The price you pay is latency (each stage adds time and you can’t always overlap them perfectly), context loss (the LLM never hears tone of voice or hesitation, only the transcribed words), and a flatter emotional surface (the LLM doesn’t know the user is frustrated, and the TTS doesn’t naturally react to the content).

End-to-end speech models bypass the transcription step entirely. The model takes audio in and produces audio out. OpenAI’s Realtime API (built on GPT-4o), Kyutai’s Moshi, and Sesame’s CSM are the prominent examples. Because there’s no STT step and no separate TTS step, latency drops dramatically. Moshi reports response latency in the 200-300ms range which is closer to human conversation than any cascade system can reach. Prosody and emotion are also better because the model directly hears and produces audio without flattening it through text.

The tradeoff is that you give up most of the things that make cascade systems engineerable. You can’t easily inspect what the model “heard.” You can’t swap a better STT in next quarter. Tool calling and structured output are weaker because they have to be encoded into the audio modality rather than handled as text. And the cost per minute of conversation is currently much higher than running a small fast LLM in a cascade.

For most production voice agents in 2026 customer service, telephony, voice front-ends to existing systems cascade is still the right architecture. The control surface, observability, and maturity of the component ecosystem outweigh the latency advantage of end-to-end models. But for use cases where natural conversation matters more than precise tool use (companions, language tutors, hands-free assistants), end-to-end is becoming genuinely competitive. It’s worth knowing both architectures exist before you commit to one.

The rest of this post focuses on cascade because that’s where the engineering surface is most interesting.

The Latency Budget
For a voice conversation to feel natural, the total round-trip from the user finishing a sentence to hearing the first word of a response needs to be under roughly 500-800ms. Beyond that, users start perceiving a delay. Beyond 1.5 seconds, it feels broken. So, you are usually fighting against the clock to get your voice agent to feel natural.

Let’s break down where the time goes in a naive sequential implementation of a voice agent:

Stage	Typical latency
Audio capture + VAD end-detection	100–300ms
STT transcription	150–400ms
LLM Time to First Token (TTFT)	300–800ms
TTS first audio chunk	100–300ms
Network overhead	50–150ms
Total	700ms–1.95s
Even at the optimistic end, you are already at the edge of acceptable. At the pessimistic end, it feels like talking to someone with a bad phone connection. This is why voice agents are fundamentally a latency engineering problem, not just an AI problem. The best voice experiences are built by teams that treat milliseconds as a first-class engineering concern.

The solution isn’t to make each stage faster in isolation (though that helps). The real unblock is streaming so that the stages can overlap rather than run sequentially.

Streaming: The Only Way to Win on Latency
In a naive pipeline, you wait for the user to finish speaking, wait for the full transcript, send it to the LLM, wait for the full response, then send it all to TTS. That’s fully sequential and the latency compounds.

In a streaming pipeline, you start TTS as soon as the LLM starts generating tokens and you don’t wait for the full response. The LLM streams token by token, and the TTS system consumes those tokens and begins synthesizing audio in real time, typically buffering 5-15 tokens before generating the first chunk of audio to avoid stopping and starting.

The voice agent pipeline: from end of user turn to first audio chunk of response

The result is that the user hears the first word of the response while the LLM is still generating the second sentence. This is how production voice systems at companies like ElevenLabs’ Conversational AI, Bland.ai, and Retell AI achieve sub-600ms end-to-end response latency despite using powerful LLMs under the hood.

Half-Duplex vs Full-Duplex
This is one of the most important architectural decisions in voice agent design, and it’s underappreciated.

Half-duplex is the push-to-talk model: one party speaks, then the other speaks. The system listens while the user talks, then responds, then listens again. Simple to implement. Feels like leaving voicemails back and forth. For simple command-response interfaces (think: “set a timer for 5 minutes”), half-duplex is fine. For natural conversation, it’s frustrating.

Full-duplex is how human conversations actually work: both parties can speak simultaneously, interrupt each other, say “uh-huh” mid-sentence, and react in real time. Building this is substantially harder. It requires the system to be listening and generating audio at the same time which means you need to solve the barge-in problem.

Barge-in is what happens when the user starts speaking while the agent is still talking. In a well-designed full-duplex system, the agent detects that the user has started speaking (via VAD), immediately stops its own audio output, cancels any pending TTS chunks, and begins processing the new input. In a poorly designed system, the agent just keeps talking while the user is trying to interrupt, which is deeply annoying.

The technical challenge of barge-in is threefold. First, you need a Voice Activity Detection (VAD) model that can distinguish the user’s voice from the agent’s own audio playback through the speaker, otherwise the agent hears itself and thinks it’s being interrupted. Second, you need to handle the latency gracefully: the moment VAD fires, you need to cut audio within milliseconds, not 300ms later. Third, you need to decide what to do with the partial audio captured during the barge-in. The question is: is it a real input or accidental noise?

The current state of the art uses Silero VAD, a lightweight neural VAD model that runs locally with very low latency (~10ms per 32ms audio chunk). Combined with echo cancellation (filtering out the agent’s own audio from the mic), it gives you a reasonable barge-in detection system.

Turn-Taking Management
Humans don’t just talk and listen in strict alternation. We use backchannels (“mm-hmm”, “yeah”), we start talking slightly before the other person has fully finished, and we use prosodic cues (pitch, rhythm, trailing off) to signal turn-yielding. Current voice agent systems handle this clumsily.

The naive approach is energy-based end-of-speech detection: wait for N milliseconds of silence before deciding the user has finished speaking. The problem is that 500ms of silence is natural in thoughtful speech it doesn’t mean the user is done. Wait too long and the agent feels unresponsive. Wait too short and it cuts off the user.

Better approaches combine silence detection with prosodic analysis (does the pitch fall in a pattern consistent with sentence completion?) and semantic analysis (does the transcript so far form a complete thought?). Some systems use a small, fast LLM to predict whether the user’s utterance is likely complete given the transcript so far, which works surprisingly well.

This is an active research area and the LiveKit Agents framework supports pluggable turn detection strategies including model-based approaches.

The Full Architecture
A production voice agent pipeline typically looks like this:

Real-time voice agent architecture: a streaming loop that listens, thinks, and speaks

The conversation state (history, memory, context) lives in the LLM prompt, which gets reconstructed for each turn. The audio transport layer (how audio bytes travel between the user’s device and your server) is typically handled by WebRTC for browser-based agents or SIP/RTP for telephony-based ones.

A Minimum Viable Voice Agent
To make this concrete, here is roughly what wiring up a voice agent looks like in practice. This is a simplified Pipecat-style pipeline showing how the pieces snap together — production code adds error handling, observability, and a lot more configuration, but the architecture is the same.

from pipecat.frames.frames import LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAILLMService
from pipecat.services.cartesia import CartesiaTTSService
from pipecat.transports.services.daily import DailyTransport
from pipecat.vad.silero import SileroVADAnalyzer

async def main():
    # WebRTC transport with built-in VAD and echo cancellation
    transport = DailyTransport(
        room_url, token, "Voice Bot",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            transcription_enabled=False,
        ),
    )

    # Three pipeline stages
    stt = DeepgramSTTService(api_key=DEEPGRAM_KEY)
    llm = OpenAILLMService(api_key=OPENAI_KEY, model="gpt-4o-mini")
    tts = CartesiaTTSService(api_key=CARTESIA_KEY, voice_id=VOICE_ID)

    # Voice-specific system prompt (more on this below)
    messages = [{
        "role": "system",
        "content": "You are a voice assistant. Keep replies short and natural."
    }]

    # Wire the pipeline: audio in → STT → LLM → TTS → audio out
    pipeline = Pipeline([
        transport.input(),
        stt,
        LLMMessagesFrame(messages),
        llm,
        tts,
        transport.output(),
    ])

    task = PipelineTask(pipeline)
    await PipelineRunner().run(task)
That’s it. Forty lines and you have a streaming voice agent that handles VAD, echo cancellation, barge-in, and full-duplex audio over WebRTC. The complexity hidden inside DailyTransport, SileroVADAnalyzer, and the streaming services is enormous, but the application code stays small. Frameworks like Pipecat and LiveKit Agents have done the heavy lifting on the orchestration so you can focus on the parts that are actually unique to your product.

Choosing Your Components
The right component choices depend heavily on your use case:

For lowest latency: Deepgram Nova-2 (STT), a distilled 7-8B model (LLM), Cartesia Sonic or ElevenLabs Flash (TTS). This stack can hit sub-500ms consistently.

For highest accuracy: Whisper large-v3 or AssemblyAI (STT), GPT-4o or Claude Sonnet (LLM), ElevenLabs Turbo (TTS). Accuracy is better but latency is 800ms+.

For telephony deployment: Twilio handles audio transport, Deepgram for STT, small LLM, ElevenLabs or AWS Polly for TTS. The PSTN (phone network) introduces its own latency — typically 150-200ms of jitter buffer alone — so your target response time needs to account for it.

For fully self-hosted, privacy-first: Whisper.cpp (local STT), Llama-3 via Ollama (local LLM), Coqui/VITS or Piper (local TTS). Excellent for private deployments; latency depends on your hardware.

What the LLM Prompt Looks Like
Voice-specific prompt engineering deserves a mention. Responses need to be designed for speech, not text. That means:

No markdown formatting, bullet points, or headers. These appear verbatim in TTS and sound bizarre
Short sentences and natural cadence. Long complex sentences with many sub-clauses are hard to follow when spoken
Avoid lists and use “first… then… finally…” constructions instead
Contractions and casual register feel more natural in speech
Build in filler words sparingly (“let me check that for you”) when computation will take a moment
SYSTEM_PROMPT = """You are a voice assistant. Your responses will be spoken aloud.
Follow these rules strictly:
- Respond in natural conversational language, as you would speak it
- Never use bullet points, numbered lists, headers, or markdown
- Keep responses concise — 2-4 sentences for most answers
- Use natural speech patterns with contractions (you are, it is, I will)
- If you need more time to think, say 'let me think about that for a moment'
"""
The Hard Problems That Remain
The basic pipeline I have described is well-understood at this point. The hard problems are what separate mediocre voice agents from good ones.

Noisy environments are the underrated killer of voice agents. A user calling from a coffee shop, or with background TV noise, or with kids in the same room sees STT accuracy drop substantially. The model still produces a transcript, but it’s wrong, and the LLM responds confidently to a query the user never asked. Tools like Krisp and RNNoise help significantly with stationary noise (HVAC, fans, traffic), but non-stationary noise (other voices, music with vocals, sudden loud sounds) is much harder. You can paper over this with voice-specific prompting that asks the user to repeat themselves when confidence is low, but it’s a workaround, not a solution.

Multi-speaker scenarios are the situation almost no production voice agent handles correctly. Imagine a family customer service call: spouse and kid in the same room, both occasionally chiming in. The agent’s STT will produce a Frankenstein transcript blending all three voices, and the LLM will respond to a query that nobody actually asked. Speaker diarization (figuring out who said what) is the answer. Pyannote-audio is the dominant open-source option, but adding it costs 200-400ms of latency on every turn and the accuracy on short utterances is still poor. Most teams just don’t solve this.

Long conversations hit context-window limits faster than text agents because every utterance needs to be transcribed, stored, and fed back as context for every subsequent turn. A 30-minute support call is easily 6,000-10,000 tokens of conversation history alone, before any system prompt or RAG context. You need a memory architecture that summarizes older turns, extracts persistent facts, and reloads relevant context on demand and crucially, all of that has to fit inside the same 500ms latency budget. This is one of the harder engineering problems in the space.

Accents and speaking styles vary STT accuracy dramatically. A model that scores 5% WER on a benchmark of American English speakers might score 15% on Indian English, 20% on Nigerian English, and 30% on heavily accented non-native speakers. Deepgram and AssemblyAI have improved substantially here, but if your product is global, you need to test specifically on the accents your users actually have, not the benchmarks the vendors quote.

The Road Ahead
This primer covers the architecture. The interesting engineering is in the details. In future posts I’ll go deep on the latency stack and where every millisecond actually goes, the barge-in problem and how production systems solve full-duplex correctly, building memory layers that survive within the latency budget, evaluating voice agents (which standard LLM evals completely miss), telephony infrastructure including WebRTC versus SIP and the codec choices that matter, and how modern TTS expresses emotion and prosody.

The voice agent space is moving fast and frameworks like LiveKit, Daily, and Pipecat have made the infrastructure significantly more accessible than it was even 18 months ago. The architectural patterns are converging. The challenge now is in the details: making the latency actually feel like presence, making the memory actually feel like continuity, and making the turn-taking actually feel like a conversation.

===================================================

PART B :

Memory in Voice Agents Is a Harder Problem Than You Think

The first time I tried to plug a memory layer into a voice agent, the thing slowed down by hundreds of milliseconds on the first turn and never recovered. The conversation went from natural to “is the line still there?” in a single round-trip, because I had ported a text-agent memory architecture wholesale: a synchronous vector lookup against a hosted store, a small re-ranking pass, then the LLM. On a chat surface, nobody would have noticed. On voice, every turn felt like the agent was buffering before it spoke.

In the voice agents primer I flagged memory as one of the harder engineering problems in the space and promised to come back to it. This is that post. The short version: voice memory is not text memory with a tighter clock. The clock is so much tighter that the entire read/write path has to invert. Most of what you think of as “memory” cannot live in the response critical path at all. It has to be pre-loaded, pre-computed, or written after the fact.

I have spent a fair bit of time staring at memory across surfaces, reverse-engineering how ChatGPT and Claude actually do it, building the layered memory hierarchy inside the Water framework, building BYOM as a portable user-owned memory layer, and then arguing publicly that most AI products shouldn’t ship memory at all. None of those experiences quite prepared me for what voice does to the design space. This post is about the constraints, the tradeoffs they force, the four families of architectures I keep seeing in production, and the things you only learn the hard way.

Why Voice Memory Sits Differently from Text Memory
Text agents come with natural slack. The user types, sees a loading indicator, and tolerates 1-3 seconds before a response. That gap is where most memory work hides in the form of vector lookups, semantic search over past chats, even a quick summarization pass. Text trained users to wait, and you can spend that wait however you like.

Voice does not give you that gift. The expected end-to-end response is 500-800ms, and that budget includes everything: STT finalization, memory lookup, LLM time-to-first-token, TTS first-chunk synthesis, and audio delivery. If memory eats more than 50-100ms of that, the conversational rhythm breaks. A single round-trip to a hosted vector database is often 20-80ms just on the network. Add embedding computation, ANN (approximate nearest neighbor) search, and result formatting, and you have spent your entire memory budget before the LLM has seen a token.

Input format is the second wedge. Text agents receive structured prose, but voice agents receive a streaming transcript of spontaneous speech, including disfluencies, restarts, false antecedents, and corrections. Any fact extraction pipeline that worked beautifully on chat will struggle here.

Turn density is the third. Voice conversations produce shorter, faster, less information-dense turns, typically 10-30 words. A 10-minute call lands at 40-60 turns and 1500-2000 tokens of transcript on average. That sounds manageable until you consider how audio inflates it on speech-native models. OpenAI’s own Realtime API cookbook is blunt: “in practice you’ll often see ≈ 10× more tokens for the same sentence in audio versus text”, and gpt-realtime caps at a 32k window. A modest support call is enough to put you on the wrong side of that line.

The fourth wedge usually gets ignored: the cold-start problem. On a chat surface you almost always have an authenticated session. On telephony voice, you often start with nothing but a phone number and have to identify the caller in the first few hundred milliseconds. Memory architectures that assume “you know who the user is at turn one” are fragile. The good ones make the unknown caller case the base condition.

The Memory Layers That Actually Matter
Three layers are worth caring about, and they line up with how the survey literature talks about agent memory more broadly. The recent “From Storage to Experience” survey frames the same evolution as Storage -> Reflection -> Experience. Letta’s product docs codify roughly the same split as Core -> Recall -> Archival. The labels change, but the layers don’t.

Conversation memory is the current call’s transcript and turn ordering, living in the LLM context window. A long call will overflow a practical 4-8k window before you notice, even though modern models nominally support 128k+ tokens. Stuffing the entire transcript into context slows generation and degrades the model’s effective attention on the parts that matter.

Session facts is the working memory layer. Things established during the current call that have to be carried forward inside it. “The caller’s name is Priya. They are calling about account 4821. They sound frustrated.” This is what the agent must not re-ask for five turns later. Without it, voice agents come across as goldfish, and goldfish behavior is the single fastest way to destroy trust on a phone call.

User profile is the long-term layer. Persistent facts across conversations. Name, preferences, last-call summary, open issues, relationship context. This is what lets a returning caller feel recognized rather than restarting from zero.

The hard design question is the middle two layers: how do you capture and surface session facts within a call, and how do you persist and retrieve user profile information across calls, both under the latency constraints above?

Where the Latency Actually Goes
Let’s make the constraint concrete. A typical voice agent response cycle looks like this:

User stops speaking -> VAD detects end of turn (~100ms)
Final transcript arrives from streaming STT (~50ms after VAD)
Memory retrieval runs (how long?)
LLM receives augmented prompt -> TTFT (~300ms for a fast model)
TTS first audio chunk (~100ms after first tokens)
Total target: ~600ms from end of user speech to first audio
Step 3 is where memory lives, and it has to fit in roughly 50-100ms to stay under that 600ms total.

That immediately rules out most of the obvious approaches. A synchronous vector search at turn time runs 30-100ms for the query, plus another 50-100ms for embedding, ranking, and formatting. Mem0’s own voice agent memory guide puts semantic search at “50-200ms depending on your vector store and infrastructure”. Even Zep, engineered specifically for low-latency context retrieval, advertises P95 of <200ms standalone and <250ms with LiveKit voice agents. Those numbers are great for chat. For voice they live at the very edge of acceptable, and only on the median, never the tail. An LLM-based summarization pass at turn time is a non-starter, 300-800ms blows the entire budget before the main LLM has even started. The one option that genuinely works is a key-value fetch from a fast in-process cache or a local Redis: 1-5ms, predictable, invisible.

The Four Questions Behind Every Voice Memory Architecture
Once you have internalized “memory work cannot live in the critical path”, the design space collapses to four decisions. You can find the same four questions implicit in every production memory system I have looked at, Letta, Zep, Mem0, A-MEM, MemoryBank, Generative Agents, even though each of them answers the questions differently. Pin them down and most of the architecture follows. (Mem0’s voice memory guide is a useful read on the same terrain if you want a vendor’s point of view.)

When do you write? Per-turn (fact-extract after every exchange) or per-session (batch at end-of-call). Per-session is cheaper and produces cleaner extractions because the model sees the whole arc. Per-turn is more expensive and noisier, but durable: if the process crashes mid-call, the WebRTC session dies without a clean disconnect, or the end-of-call extraction itself fails, per-session loses everything for that call while per-turn keeps every fact written through the last successful turn. Almost every production voice deployment I have seen accepts the cost penalty and runs per-turn, because abnormal terminations are routine in telephony and “we lost the transcript” is not a failure mode you want to debug live. (A third option, sleep-time writes, gets its own section below.)

What do you write? The question I would ask of every candidate fact is: would this actually change how the agent responds in a future session? If not, it’s noise, and noisy memory hurts more than absent memory because it makes retrieval less precise on the things that do matter. In practice this means the more specialized your use case, the more aggressive your filtering should be. A general assistant can afford generic LLM driven extraction. A medical intake agent should be writing into a typed schema and rejecting anything that doesn’t fit.

How do you retrieve? Four patterns dominate:

Pattern	When it works	What it costs
Dump everything	Users with <20-30 memories	Token bloat past the threshold; “lost in the middle” past long contexts
Pure semantic search	When relevance per-turn is the bottleneck	50-200ms per turn - usually too much for voice
Pre-loaded context	When the user has stable, summarizable history	Stale within long sessions; cold-start has nothing to load
Hybrid (pre-load + on-demand)	Most production voice agents	Requires a topic-shift detector, but it’s the right default
Where does the work happen? Inline, parallel (a memory agent alongside the voice pipeline), or post-processing. For voice, the answer is almost always parallel for writes and pre-loaded for reads, with inline retrieval reserved for the tightest cases.

These four answers, taken together, decide which architecture family you are in.

The Architecture Landscape
I would group the voice memory architectures I have looked at into roughly four families. They aren’t mutually exclusive but most real systems blend at least two and they make for a useful map.

Family 1: Native framework state
Every serious voice agent framework maintains conversation state inside the pipeline for the duration of a session, and the major end-to-end speech APIs do the same on their side, often with built-in context truncation. This family handles only the within session problem and nothing survives the call. Treat it as the floor of any architecture, not the architecture itself which is useful as the place to put session facts, useless for anything across calls.

End-to-end speech models collapse the STT-LLM-TTS pipeline into a single stateful session and solve the latency of pipeline problem outright, but they don’t solve the memory problem. OpenAI’s Realtime API caps at a 32k token session, Google’s Gemini Live discards session state at the end of every call, and neither has any built-in concept of cross-session persistence beyond what you wire up around them. Whatever architecture you would have built around a cascade pipeline, you still have to build around an end-to-end one. One genuine upside is that multimodal models can process audio directly, so fact extraction can operate on raw audio rather than a text approximation, which matters for any domain where paralinguistic signal (hesitation, tone, affect) actually shapes the response.

Family 2: Bolted-on memory services
This is where most teams I have talked to start: drop a third-party memory service into the pipeline as a processor between the user aggregator and the LLM, configure a user/entity ID, and let it handle the read/write loop. Mem0, Zep, Hindsight, and Supermemory all ship plugins for the major voice frameworks. The shared shape across all of them is pipeline level integration, user/entity scoping, async writes, and either pre-loaded or on-demand retrieval. The differences are mostly storage substrate (vector vs graph vs SQL), how aggressive the extraction is, and per-call ergonomics.

Family 3: Knowledge-graph memory
This is the family I find most interesting because it actually changes what “memory” means, not just how fast you can fetch it. Instead of embedded text chunks retrieved by similarity, knowledge-graph systems store entities, relationships, and temporal validity, and retrieve by graph traversal augmented with semantic search. The model gets “John’s favorite song is ‘Viva La Vida’ by Coldplay (valid: 2024-01-15 to present)” instead of three loose chunks of past dialog. The production option I have seen show up most often is Zep’s Graphiti; the most interesting academic entry is A-MEM (NeurIPS 2025), which writes each memory as a Zettelkasten-style note that other memories can update over time, so the graph is actively reorganized rather than just appended to. The cost is complexity: graphs are harder to debug, harder to evict from, and more expensive to build than a flat vector index, but for any voice agent that will be on the phone with the same user for years, this family is where the long-term answer lives.

Family 4: Cognitive architectures
The fourth family treats memory as a cognitive process and not as a database. The foundational reference is Park et al.’s Generative Agents (UIST 2023) a memory stream, a reflection step that periodically synthesizes higher-level insights, and a retrieval policy scoring candidates on recency, importance, and relevance. Reflection is the part everyone copies, because it’s what makes the agent feel like it understands you over time rather than parroting what you said. Variants add other tricks: MemoryBank introduces an Ebbinghaus-style forgetting curve so old unused memories quietly drop out; MemR3 (2025) flips retrieval into a router that decides between retrieve, reflect, and answer on each turn. These rarely ship as turnkey products. They are patterns to steal, reflection schedules, importance weighted retrieval, time-decayed scoring, and graft onto a Family 1 + Family 2 base.

Inverting the Read/Write Path
The pattern that actually works in production, regardless of which family you pick from above, is to split memory operations into two categories: things that happen before the response (retrieval) and things that happen after the response (writing). Keep only the absolutely essential retrieval in the critical path, and make even that as fast as possible through pre-loading.

Pre-load at conversation start. When a call begins, before the user says a word, you have a few hundred milliseconds of setup time, WebRTC connection, audio initialization, codec negotiation. Use that window to fetch the user’s profile, their last-call summary, and any open issues into a session-local cache. When the first turn arrives, your “memory retrieval” is a dictionary lookup, not a network call. Every millisecond you spend fetching profile data on turn one is a millisecond the user spends listening to silence.

The cold-start case is where this gets real. If the caller is anonymous, you can’t pre-load anything user-specific. You either authenticate them in the first turn or two (account number, CRM phone-number lookup during setup) or accept thinner context on the first call and design the prompt to be graceful about it. The mistake I see most often is teams treating authenticated as “the system” and anonymous as an edge case. In telephony, anonymous is a hot path.

The other half of the inversion is async writes. After each response, kick off a fire-and-forget background task that extracts new facts from the latest turn and persists them. By the time the call ends, the profile is largely up to date and none of that work has spent any of your inner-loop latency budget. To handle short calls that hang up before extraction finishes, block the call-end handler on a small timeout (2-3 seconds is usually fine) so in-flight tasks drain. The user has already gone, so there is no latency budget to defend. Then run a full summarization pass over the entire transcript and store it as the canonical record like what the call was about, whether it was resolved, key facts, follow-ups. That summary becomes the last_interaction you pre-load on the next call, and it is the single most underrated artifact in a voice memory system. Both ChatGPT and Claude lean on the same idea in their text systems: a curated summary beats a raw transcript at retrieval time, every single time.

Two things bite you once you actually ship this. First, the pre-load can race the previous call’s writebacks. Imagine a caller asks to be called Alex on one call: the per-turn extraction captures “please call me Alex” and persists it. If the next call’s pre-load reads from a snapshot taken a few seconds before that writeback finished draining, the agent greets them by their old name which erodes trust faster than no memory at all. The fix is the obvious one (always serve the freshest writeback even if your snapshot is older), but the failure mode only shows up once you have real users. Second, per-turn extraction means an extra LLM call on every single turn. At a few cents per call multiplied by 40-60 turns, a 10-minute conversation can land at a couple of dollars in extraction alone which is fine for a high-value support call, ruinous for a free consumer assistant at scale. The honest move is to pick a cheaper model for extraction (a distilled 7-8B is usually plenty), run extraction on a longer rolling window, or bias toward post-call extraction for low-margin use cases.

Compressing Conversation History Within a Call
Even within a single call you will hit the practical context limit faster than you expect. A 10-minute call at normal pace lands at 1500-2000 tokens of transcript alone, and on a speech-native session the 10× audio token inflation pushes you well past where any large context advertisement actually holds up.

The mitigation is a rolling window with summary: keep the last N turns in full, replace earlier turns with a compressed summary. When the transcript hits a threshold (say, 20 turns), kick off an async compression pass that replaces the first 10 with 3-4 sentences. Use a fast small model for this, a distilled 1-3B on a colocated GPU, or a fine-tuned summarizer on CPU. 50-150ms per compression is fine async but would be painful in the critical path.

Selective retention is the other lever. Not all turns are equally valuable “okay”, “got it”, “mm-hmm” contribute close to nothing. Even a length and stopword heuristic, much less a tiny classifier, can drop low-signal turns without losing content. Treat the transcript as something to curate, not a log to preserve.

Long-Term Episodic Retrieval
For structured profile data like name, preferences, known issues, a key-value store is the right answer. Fast, predictable, no embedding required. This is the boring part of memory and it should stay boring.

For unstructured episodic memory that is specific past conversations, detailed historical interactions, you eventually need semantic retrieval. The question is when to do it, and the answer is: not during a turn.

The pattern that works is background relevance preparation. You maintain a representation of the current conversation topic. In practice this is usually the last one or two user turns embedded as a single query vector, sometimes augmented with a small classifier-derived topic label. Periodically, every 3-5 turns, or whenever the topic vector shifts beyond a threshold, you fire an async retrieval query against past conversations. If the retrieval finds something relevant, the result gets staged for injection on the next turn, not the current one.

That introduces a one-turn lag on episodic context, and that tradeoff is almost always the right one. Users won’t notice that the agent referenced a past conversation a beat after the topic came up. They will absolutely notice if every turn has a 200ms hesitation.

The honest counterpoint is rapid topic shift. If a user pivots topics every turn which happens more in casual support calls than you would expect your staged retrieval is constantly stale. The pragmatic fix is to detect the shift cheaply (cosine similarity drop between consecutive query vectors) and fall back to a “no episodic context” path rather than injecting yesterday’s topic into today’s question. Stale context is worse than absent context.

Sleep-Time Memory Consolidation
Per-turn writes plus end-of-call summarization handle the basics. The next-level move is doing memory work between sessions, while the system is idle. The clearest articulation of this is Letta’s sleep-time compute, which spawns a separate agent that shares memory blocks with the user-facing agent and runs in the background, reorganizing and consolidating what’s there. The paper that motivated it reports a ~5× test-time compute reduction at equal accuracy and 13-18% accuracy lifts when queries are predictable. Those are the paper’s headline numbers on their chosen benchmarks; for voice, the more useful framing is that even modest consolidation work between calls pays back in retrieval quality on the next one.

The intuition for voice is straightforward. Per-turn writes give you a flat, time-ordered stream of facts. Over weeks and months, that stream accumulates contradictions (“user prefers email”… “user said please call them”) and stale context. A nightly sleep-time consolidation pass can merge duplicates, resolve contradictions in favor of the more recent signal, prune low-importance memories with a forgetting-curve schedule, and synthesize higher-level reflections in the spirit of Park’s Generative Agents — “this user tends to call when something is broken, not for general questions.”

The reason this matters specifically for voice is that you cannot afford to do any of this consolidation work in the critical path. Sleep-time is the only place in the architecture where you have unlimited latency budget. Anything you don’t do here, you’ll regret doing inline.

Clean Signal: Transcripts and Multiple Speakers
All of this assumes the input to your memory pipeline is reasonably clean. In practice it isn’t, and there are two distinct problems hiding in there: noisy transcripts of the caller’s own speech, and the fact that there’s often more than one person in the room.

On the first: voice transcripts are messy. Users say “um” and “uh”, they restart sentences, they use pronouns without antecedents (“tell me about that thing we talked about”). Raw transcripts make for noisy fact extraction. The mitigation is a lightweight transcript cleaning step, a fast pass that removes disfluencies and normalizes references before passing the text into any memory pipeline. This runs asynchronously and never touches the response cycle. The LLM itself sees the raw transcript (because cleaning it adds latency you cannot afford), but memory extraction works off the cleaned version.

The second problem is the one almost no production voice agent solves cleanly. Family customer service calls have a spouse and a kid in the same room. Healthcare calls have a caretaker. Inbound support from a small business has someone shouting context from across the office. Speaker diarization, figuring out who said what is what makes memory accurate here. Without it, your fact extractor cheerfully writes “caller’s spouse hates the current plan” into the caller’s profile, which destroys trust on the next call. pyannote-audio is the dominant open-source option; newer LLM-grounded systems like TagSpeech and DM-ASR show meaningful gains on overlap-heavy audio. Though the latency cost is real with 200-400ms of additional latency per turn on the critical path which is why most production voice agents I have seen don’t ship live diarization aware memory. The workable compromise is to run diarization async on the post-call recording, attribute facts to the right speaker before persisting, and accept some attribution noise within the call itself. It’s the kind of thing that goes wrong rarely enough to be acceptable and wrong badly enough that you should at least have a story for it.

The Three-Tier Stack
Putting it together, a production voice memory system has three tiers, defined by latency profile rather than what they store.

Tier 1 - hot cache (1-5ms): pre-loaded at call start. User profile, last-call summary, open issues. Lives in process memory for the call’s duration. Serves every turn lookup essentially instantly.

Tier 2 - background retrieval (50-150ms, async): episodic search between turns, results staged for injection on the next turn. Never blocks.

Tier 3 - async writes (latency irrelevant): fact extraction, profile updates, end-of-call summarization, sleep-time consolidation. Happens after each turn, after the call ends, and during system idle. Feeds Tier 1 for the next call.

Voice Memory Architecture

Notice the asymmetry: the only thing on the blocking path is the cache lookup. Everything expensive embedding, retrieval, summarization, writeback, consolidation has been pushed to the cracks between turns, to after the call has ended, or to system idle.

Closing Thoughts
Voice agent memory is still largely unsolved in the sense that genuinely human-like recall across many conversations remains elusive. The infrastructure has fast caches, async extraction, structured profiles, end-of-call summaries, knowledge graphs, sleep-time consolidation and is well-understood and implementable today, with mature frameworks (Pipecat, LiveKit Agents) and a healthy ecosystem of memory services (Mem0, Zep, Letta, Hindsight, Supermemory, Cognee) you can drop in without writing the read/write loop from scratch. The craft lives in the semantic part: deciding what to remember, when to surface it, and how to do it without sounding like the agent is reading from a file. That part rewards careful prompt design and aggressive curation of what gets persisted, not bigger vector databases.

If there’s a single line to take away: in a voice agent, the speed of memory is set by what you have already prepared, not by what you can fetch in the moment.

Next in this series I will cover evaluating voice agents, the part that standard LLM evals (and even LongMemEval and LoCoMo) miss completely, and where most of the hard won lessons from production actually live.



References
Liu, Nelson F., et al. “Lost in the Middle: How Language Models Use Long Contexts.” arXiv:2307.03172, 2023.
Park, Joon Sung, et al. “Generative Agents: Interactive Simulacra of Human Behavior.” UIST 2023.
Zhong, Wanjun, et al. “MemoryBank: Enhancing Large Language Models with Long-Term Memory.” arXiv:2305.10250, 2023.
Chhikara, Prateek, et al. “Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory.” arXiv:2504.19413, 2025.
Xu, Wujiang, et al. “A-MEM: Agentic Memory for LLM Agents.” NeurIPS 2025.
Du, Xingbo, et al. “MemR3: Memory Retrieval via Reflective Reasoning for LLM Agents.” arXiv:2512.20237, 2025.
“Sleep-time Compute: Beyond Inference Scaling at Test-time.” arXiv:2504.13171, 2025.
Luo, Jinghao, et al. “From Storage to Experience: A Survey on the Evolution of LLM Agent Memory Mechanisms.” arXiv:2605.06716, 2026.

==================================
PART C : 

How to Evaluate Voice Agents
A voice agent can pass every eval you wrote for it and still be broken in production. The transcript reads correctly, the tool call fires with the right arguments, the backend state lands where it should, and the scorecard marks the call a success. Then you listen to the actual recording and hear the agent talking over the caller, mangling their name, and leaving three seconds of dead air before it confirms anything.

I have watched that gap open up more than once, and the cause is always the same: the agent was evaluated like a text agent with a microphone attached. A voice agent is a real-time distributed system, and most of its product quality lives in dimensions a transcript simply cannot represent, like when the agent started speaking, how long the user waited, whether it yielded when interrupted, and how it sounded while doing it. An eval that only reads transcripts after the call is grading a summary of the interaction rather than the interaction itself.

When I wrote the voice agents primer, I listed evaluation as one of the things standard LLM evals completely miss and left it for a future post. A complete evaluation has to cover the call itself: choosing the right unit of evaluation, scoring the four layers of a call, working out whether your simulator and LLM judge can be trusted, and turning the results into a ship-or-don’t-ship decision.

This is the third and final part of the voice agents series, following the voice agents primer and voice agents memory.

Let’s get into it.

The Unit of Evaluation Is the Call
The naive eval stack converts the audio to text, passes that text to the LLM, and scores the response. This measures whether the agent produced a reasonable answer after transcription, but misses whether it waited too long, interrupted the user, ignored a barge-in, misheard a critical entity, sounded bored, spoke over background noise, or completed the backend action correctly.

The modern voice eval stack evaluates the live call path rather than an isolated response. This is more representative of product quality because the goal is a voice agent that feels as natural and helpful to the user as possible. Across voice eval tools, the common pattern is:

Define a scenario.
Run a real or simulated call.
Capture the full trace.
Score behavior with multiple evaluators.
Turn failures into regression tests.
A Real Eval Scenario
Consider an appointment scheduling voice agent for a clinic. A weak eval would look like this:

User: I need to move my appointment to Friday afternoon.
Expected: Agent reschedules appointment.
For a text agent, that eval may be enough to check logical correctness. For a voice agent, it omits timing, audio, turn-taking, tool execution, and business outcome, all of which contribute to product quality.

A useful eval scenario has a caller persona, audio conditions, expected tool behavior, success criteria, and failure attribution:

scenario: reschedule_existing_appointment
persona:
  name: "Impatient returning patient"
  speaking_style: "fast, interrupts once, says the date ambiguously"
  environment: "car bluetooth with mild road noise"

initial_state:
  patient_id: "p_123"
  existing_appointment: "2026-05-27 10:30"
  available_slots:
    - "2026-05-29 14:00"
    - "2026-05-29 16:30"

caller_goal:
  reschedule appointment to Friday afternoon

required_behavior:
  - verify patient identity before changing appointment
  - clarify which Friday if date is ambiguous
  - offer available afternoon slots
  - call reschedule_appointment with the selected slot
  - confirm the new appointment time out loud

failure_modes_to_track:
  - missed identity verification
  - wrong date resolution
  - wrong tool arguments
  - ignored interruption
  - response latency over 900ms p95
  - user repeats same information twice
A Passing Simulation Proves Almost Nothing
Voice agents are stochastic twice over: the model samples different responses, and borderline ASR or turn-detection decisions can change with small variations in audio. One successful call proves possibility, not reliability. Run each important scenario repeatedly and report a rate.

This is why EVA-Bench reports both pass@k and pass^k. pass@k asks whether at least one of k runs succeeds, which measures the system’s ceiling. pass^k estimates the probability that k independent runs would all succeed, which measures consistency. A system with high pass@3 and low pass^3 can produce an impressive demo, but it is not dependable enough for a workflow where every call matters.

The simulator also needs an eval. Synthetic callers are useful because they scale, but they are not automatically representative of humans. They may speak too cleanly, cooperate with clarifying questions, avoid real disfluencies, or share model family quirks with the agent under test. Validate simulator behavior against a held out set of human calls: compare task paths, interruption patterns, turn lengths, failure categories, and pass rates. If improvements on synthetic calls do not predict improvements on real calls, you are optimizing against the simulator.

Layer 1: Did It Hear the User?
ASR (automatic speech recognition) evaluation usually starts with Word Error Rate, and WER is still useful. If you swap STT (speech-to-text) providers and your domain WER jumps from 7% to 14%, you probably made the agent worse. Its business impact, however, depends on which words were transcribed incorrectly.

Substituting “a” for “the” may be harmless. Hearing “May fifteenth” as “May fifty,” dropping the word “not,” mangling a medication name, or capturing “cancel my subscription” as “cancel my description” can break the call. A single word can be the whole task.

For production voice agents, I would track three ASR metrics:

Domain WER measures transcription quality on your actual vocabulary: product names, customer names, addresses, appointment types, insurance terms, SKUs, airport codes, whatever your domain contains. Build this from real calls.

Entity error rate measures whether the fields that drive business logic were captured correctly: names, dates, amounts, confirmation numbers, addresses, and IDs. This is often more predictive than WER. A transcript can be 95% correct and still fail the call because the 5% contained the appointment time.

Streaming stability measures how much partial transcripts change before finalization. If your agent starts planning on partial ASR, final WER is too late. You need to know whether the intermediate transcript was stable enough to feed into turn detection, early intent classification, or speculative tool planning.

The subtle bug here is attribution. If ASR turns “Friday at four” into “Friday at floor,” the LLM may ask a weird clarification. A transcript-only eval misattributes this as LLM confusion; the ASR handed the model bad input.

Layer 2: Did It Manage the Conversation?
This is the part text evals completely miss.

Voice is continuous time. Users pause, breathe, backchannel, self-correct, talk over the agent, and ask a different question halfway through the answer. A good voice agent needs both answer quality and conversation control. Building the right barge-in behavior is only half the job; you also have to measure whether it works across a range of real conditions.

The research world has started catching up here. Full-Duplex-Bench evaluates pause handling, backchanneling, turn-taking, and user interruption. Its v1.5 overlap scenarios include interruption, backchannel, talking to others, and background speech, then measure whether the model stops, responds, resumes, or incorrectly holds the floor. The timing metrics are exactly the kind of thing production teams should integrate in their evals from the Full-Duplex-Bench. Stop latency when interrupted, response latency after interruption, and whether the model actually took the new user intent.

This matters because “interruption count” alone is ambiguous. A high interruption count can mean users are engaged and naturally backchanneling. It can also mean the agent is too verbose and users keep cutting it off. You need to track these categories:

End-of-speech accuracy: Did the agent detect that the user was done, or did it jump in during a pause?

Yield latency: When the user interrupted, how long did the agent keep speaking?

Backchannel selectivity: Did the agent ignore “mm-hmm” and “yeah” when they were acknowledgements, but stop for “wait, actually…”?

Agent interruption rate: How often did the agent begin speaking before the user had finished?

Silence budget: How much dead air did the user experience across the whole call, especially at p90 and p99?

This is where a lot of “the model is bad” complaints are actually VAD, endpointing, or turn detection complaints. If the endpointer fires too early, the agent responds to half a sentence. If it fires too late, the call feels sluggish. If barge-in is too sensitive, the agent stops for coughs and background TV. If it’s too conservative, the user feels trapped.

Measure the Latency Waterfall, Not Just the Total
End-to-end latency measures how long the user waited, while tracing each pipeline stage identifies the cause. Trace a single turn from the moment the user stops speaking, to the endpointer deciding the turn is actually over, to a stable ASR transcript, to the LLM’s first token (or, on a tool turn, the completed tool call, the tool’s own execution, and the model’s second pass afterward), to the first frame of synthesized audio, and finally through the network buffer and playback until the user actually hears something. In practice these stages overlap rather than run in a neat line, which is exactly why you want them captured as trace spans instead of a single number.

The one metric that represents the product is end-of-turn time to first audio (TTFA), measured from the user finishing their turn to the first audible response reaching them, and you want it at p50, p95, and p99. Everything else in the trace is a diagnostic. A slow call might come from conservative endpointing, unstable partial transcripts, the LLM’s time to first token, tool-call generation, a tool’s tail latency, the post-tool model pass, TTS startup, or the jitter buffer, and until you can see the breakdown you can’t tell which one to fix. Without it, teams tend to optimize whichever component is easiest to see on a dashboard rather than the one actually costing the user their time.

Tool-using turns need special treatment because they can contain two silences: one before an acknowledgement and another while the tool runs. Measure both. A fast first acknowledgement can make the interaction feel responsive even when the backend operation takes longer, but it must not become fake reassurance before the tool has succeeded.

Layer 3: Did It Think and Act Correctly?
Once the agent has heard the user and managed the turn, evaluate reasoning and action through four checks.

Intent and state tracking: Did the agent understand what the user wanted, and did it preserve the relevant state across turns? In voice, the same intent often arrives over multiple messy fragments: “I need to move it… no not tomorrow… the Friday one… afternoon if you have it.” The eval should verify the final state, not just each turn.

Tool-call correctness: Did the agent call the right tool at the right time with the right arguments? This should be structured, not judged from prose.

Business outcome: Did the backend state actually change correctly? Success means the appointment moved, the refund was issued, the ticket was created, or the transfer reached the right queue, not merely that the agent said “you’re all set.”

Policy and safety: Did the agent follow the rules that matter in your domain? Healthcare, finance, insurance, and recruiting agents all have steps that can’t be “mostly right.” Identity verification, consent, disclosure, escalation, and PII handling need hard pass/fail assertions.

This is where LLM-as-judge is useful, but only if the rubric is specific. “Was the agent helpful?” is weak. “Did the agent verify identity before revealing appointment details?” is strong. “Did the agent explain that cancellation fees apply before completing the cancellation?” is strong. “Did the agent avoid promising a refund before checking eligibility?” is strong.

Good judges are boring. They read like QA checklists.

Your Judge Needs an Eval Too
An LLM judge is another model in the system, not ground truth. Before using one as a release gate, build a human-labeled calibration set from real calls and measure agreement for each rubric dimension. Track false passes separately from false failures: a judge that occasionally underrates politeness is annoying but a judge that misses policy violations is dangerous.

For subjective comparisons such as naturalness or concision, pairwise judgments are often easier to calibrate than absolute scores. Run both A/B and B/A orderings because judges can systematically prefer one presentation position. Pin the judge model, prompt, rubric, and version alongside every score, then rerun calibration when any of them changes. Recent large-scale work on judge reliability found that high test-retest consistency can coexist with meaningful position bias, which is exactly why “the judge gives stable scores” is not enough validation.

Structured facts should not go through an LLM judge at all. Tool name, arguments, ordering, backend state, latency, and explicit verification or disclosure events should be checked directly when the trace represents them. If compliance exists only in the conversation’s semantics, use a calibrated judge or human review. Save model judges for dimensions that genuinely require interpretation.

Layer 4: Did It Sound Good?
TTS quality is still weirdly under evaluated in voice products. Teams will A/B test three LLM prompts for a week and then pick a voice because it sounds acceptable in the dashboard preview. That’s not enough once calls get long.

The generated audio needs its own evaluation pass. Start with the obvious checks: clipping, dropouts, volume swings, weird pauses, repeated audio loops, pronunciation failures, and latency to first audio. Once those are covered, you still need an automated score for naturalness, because nobody can listen to every call. The speech research community has a few models that try to predict how a human would rate a clip, and they are useful as filters even if they are not perfect judges.

The shared idea behind most of them is MOS, mean opinion score. In classic listening tests, people rate speech on a 1 to 5 scale from bad to excellent, and the average of those ratings becomes the MOS. Listening tests do not scale, so teams use neural models trained to approximate that human score from the audio itself.

UTMOS is one of those predictors, built specifically for synthesized speech. You give it the agent’s TTS audio and it returns a MOS-like naturalness score. Think of it as a quick answer to “does this voice sound human, or does it sound like a robot reading from a script?” It is useful for comparing voices and spotting regressions after a TTS change, but it will not tell you whether a phone number was pronounced wrong.

NISQA and its TTS variant NISQA-TTS go further by scoring speech quality without needing a clean reference recording to compare against. That matters in production because you usually only have the call that went out, not a perfect original. Beyond a single overall score, NISQA breaks quality into dimensions like noisiness, coloration, discontinuity, and loudness, which helps you separate “the voice sounds robotic” from “the call path is mangling the audio.” Use it when you want more than a naturalness number and need a hint about why the audio feels bad.

DNSMOS is aimed at a different problem: audio that has already been through noise suppression, telephony codecs, or otherwise degraded channels. If your agent runs over phone lines, Bluetooth, or a noisy room, DNSMOS is often a better fit than a model trained mostly on clean studio speech. It helps answer whether the delivery path is hurting intelligibility, not just whether the TTS voice itself is pleasant.

Reverse ASR is the blunt, practical check for the thing those naturalness models miss. Take the text the agent intended to say, synthesize it with TTS, then run a strong speech-to-text model over the resulting audio and compare the transcript back to the original text. If the agent meant to say “May fifteenth” and the round trip comes back as “May fifty,” the TTS pronounced it wrong even if the clip still scored well on naturalness. This is crude, but it catches word-level failures that MOS predictors routinely miss.

The frontier is moving toward learned speech judges. SpeechJudge builds a human preference dataset of speech pairs and trains a generative reward model for naturalness judgment. Its results show that even strong audio models still struggle to match human naturalness judgments: SpeechJudge-GRM reaches 77.2% accuracy on its benchmark, rising to 79.4% with inference-time scaling.

So use automated audio metrics as filters, not final truth. The last mile still needs humans listening to real calls.

The Harness I Would Build
If I were building voice-agent evals from scratch, I would start with five datasets.

The first is a golden scenario set: 50-100 hand-written scenarios covering your core user journeys. Each scenario has a persona, initial backend state, expected tool calls, expected final state, and policy requirements. This is your CI suite.

The second is a real-call regression set: production calls that failed, got escalated, received bad CSAT, or triggered manual review. Preserve the audio, timing, transcript, tool trace, and outcome. This is the most valuable dataset you will own.

The third is a perturbation and resilience set: the same core scenarios under accents, background noise, fast speech, long pauses, interruptions, far-field audio, telephony codecs, and Bluetooth style degradation, plus packet loss, jitter, reconnects, tool timeouts, delayed webhooks, and partial backend failures. It should verify that retries do not duplicate bookings or payments and that an interrupted call cannot leave the backend in an ambiguous state.

The fourth is a held-out release set: representative scenarios that prompt authors, simulator tuning, and judge calibration never use directly. Regression suites eventually become something teams optimize against. A private release set tells you whether the new build actually generalized or merely learned the tests. Because repeated release decisions still leak information through model selection, rotate this set periodically and keep a smaller untouched audit set for major releases.

The fifth is a human audit sample: 10-20 calls per week that someone actually listens to. Not reads. Listens. The ear catches awkwardness that transcripts hide, and those reviews provide the labels needed to keep simulators and automated judges honest.

For every run, store the same trace shape. Group it by what you will eventually need to debug:

Category	What to store	Why it exists
Identity	call_id, scenario_id, build and provider versions	so you can rerun the exact same system later
Audio	inbound and outbound audio, TTS chunks with timestamps	so humans and audio judges can listen to the real call
Hearing	partial and final ASR transcripts, entity extractions, confidence	so you can tell whether the model was confused or handed garbage
Turn-taking	VAD events, endpointing decisions, interruption marks	so you can measure yield latency and barge-in behavior
Reasoning	LLM inputs and outputs, tool calls and results	so you can assert intent, arguments, and policy steps
Timing	latency timeline, transport events, retries	so a slow call decomposes into a waterfall instead of a single number
Outcome	final backend state, judge scores, human review notes	so “you’re all set” is checked against what actually changed
That trace is also a privacy liability. Raw audio may contain biometrics, payment details, health information, addresses, and anything else a caller says aloud. Treat audio, unredacted transcripts, redacted transcripts, metadata, and aggregate metrics as separate retention classes. Redact before broad search or analytics, restrict access to raw traces, and record which third-party STT, LLM, TTS, and judge services received the data. The eval system should not become the least governed copy of your production calls.

Layer	What to Score	Example Gate
ASR	entity error rate, domain WER, partial stability	critical entities correct
Turn-taking	endpointing, yield latency, backchannel selectivity	yield within 500ms on interruption
Agent reasoning	intent, state tracking, policy compliance	required verification completed
Tools	tool name, arguments, ordering, final state	backend state matches expected
Audio output	TTFB, naturalness, artifacts, pronunciation	no clipping/dropouts, terms pronounced correctly
Outcome	task success, escalation correctness, user sentiment	scenario passes business goal
Turn Scores Into a Release Decision
Don’t average every metric into one reassuring number. Policy, safety, identity verification, required disclosures, tool arguments, and final backend state all need hard gates: one severe violation fails the scenario regardless of how good the latency and naturalness look. Use thresholds for latency, ASR, and audio artifacts, then reserve weighted or preference scores for softer qualities such as tone and concision.

Run critical scenarios multiple times and block on reliability, not the best attempt. Report the pass rate with its sample count and confidence interval; a 90% result over ten calls is not the same evidence as 90% over a thousand. Track flake rate explicitly, because a build that becomes demonstrably more reliable may be more valuable than one that slightly improves the average judge score.

Slice every important metric by language, accent, device, codec, region, call length, intent, and customer cohort. Aggregate WER, latency, or task success can hide failures concentrated in one of these groups. Release reports should show both the overall number and sufficiently sampled worst-performing slices, with sample counts and uncertainty. Users experience their slice, not your average. The useful metrics are the ones that point to action.

If entity error rate fails, inspect ASR and domain vocabulary. If yield latency fails, inspect VAD, AEC, barge-in, and audio playback cancellation. If tool arguments fail, inspect state tracking and schema design. If naturalness fails, inspect TTS voice, text chunking, pronunciation dictionaries, and response length. If task success fails but all component metrics pass, your scenario design or business workflow is probably wrong.

The Production Loop
When a real call fails, do not merely tag it in a dashboard. Replay fixed audio where the conversational path can remain fixed, such as ASR, audio, and component tests. For end-to-end regression, preserve the failure’s conditions and intent in an adaptive scenario so the synthetic caller can respond when a changed agent takes a different path.

In practice the loop is continuous. You ship a build, monitor real calls, find a failure, label the root cause, turn that failure into a regression test, fix the underlying issue, rerun the suite, and only then ship again. The regression is the part most teams skip. Without it, the same failure can reappear three releases later and look like a new bug.

Over time, your eval set becomes a map of every strange thing users actually do: the person calling from a car, the user who interrupts every sentence, the caller who says “yeah” as a backchannel, the customer with a noisy TV in the background, the patient who gives a date without a year, the angry user who refuses to follow the happy path.

Regression sets need maintenance. Deduplicate near-identical failures, preserve the original raw case and its normalized or adaptive test, version scenarios and rubrics, and keep the held-out release set separate from day-to-day prompt tuning. Otherwise the suite grows slower while the team gradually overfits to a museum of old incidents.

That maintained dataset is more valuable than any generic benchmark.

Parting Words
Voice eval is hard because the product is the whole live interaction: what the user said, what the system heard, when the agent responded, how it sounded, whether it yielded, which tools it called, and what changed in the real world.

So evaluate the call, not the text.

References
ServiceNow. EVA-Bench: A New End-to-End Framework for Evaluating Voice Agents. arXiv, 2026.
Norman, Justin D., Michael U. Rivera, and D. Alex Hughes. Reliability without Validity: A Systematic, Large-Scale Evaluation of LLM-as-a-Judge Models Across Agreement, Consistency, and Bias. arXiv, 2026.
ElevenLabs. Voice Agent Latency Optimization.
Hamming AI. Voice Agent Log Retention Compliance Checklist.
Chen, Yiming, et al. VoiceBench: Benchmarking LLM-Based Voice Assistants. arXiv, 2024.
Yang, Qian, et al. AIR-Bench: Benchmarking Large Audio-Language Models via Generative Comprehension. ACL, 2024.
Yan, Ruiqi, et al. URO-Bench: A Comprehensive Benchmark for End-to-End Spoken Dialogue Models. arXiv, 2025.
Wang, Ke, et al. VoiceAssistant-Eval: Benchmarking AI Assistants across Listening, Speaking, and Viewing. arXiv, 2025.
Liu, Heyang, et al. VocalBench: Benchmarking the Vocal Conversational Abilities for Speech Interaction Models. arXiv, 2025.
Lin, Guan-Ting, et al. Full-Duplex-Bench: A Benchmark to Evaluate Full-duplex Spoken Dialogue Models on Turn-taking Capabilities. arXiv, 2025.
Lin, Guan-Ting, et al. Full-Duplex-Bench v1.5: Evaluating Overlap Handling for Full-Duplex Speech Models. arXiv, 2025.
Li, Yangzhuo, et al. WavBench: Benchmarking Reasoning, Colloquialism, and Paralinguistics for End-to-End Spoken Dialogue Models. arXiv, 2026.
Zhang, Xueyao, et al. SpeechJudge: Towards Human-Level Judgment for Speech Naturalness. arXiv, 2025.
Mittag, Gabriel, et al. NISQA: A Deep CNN-Self-Attention Model for Multidimensional Speech Quality Prediction with Crowdsourced Datasets. Interspeech, 2021.
Reddy, Chandan K. A., et al. DNSMOS P.835: A Non-Intrusive Perceptual Objective Speech Quality Metric to Evaluate Noise Suppressors. arXiv, 2021.
Ribeiro, Maurício, et al. UTMOS: UTokyo-SaruLab System for VoiceMOS Challenge 2022. arXiv, 2022.