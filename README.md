## Local Email Agent (WIP)

The idea for this came to me during a New Year’s Eve party. Admittedly, not completely sober, I thought:  
> *"It sucks that I write my emails using OpenAI — I don’t want to end up in their training data."*  

Also, I had just picked up a new MacBook Air and wanted to try out Ollama. So the concept was born:  
A local, privacy-preserving email assistant that helps me summarize and write emails without leaving my machine.

### Goals

- Generate summaries of incoming emails
- Produce a daily status update
- Extract email importance and deadlines
- Automatically sort emails into mailboxes (if specified)
- Detect meeting proposals and check calendar availability
- Use existing conversation history to generate iterative drafts
- Improve generation quality via multi-shot prompting using your past edits, classifications, and summaries

### Motivation

The models aren’t fully there *yet*, but given the exponential progress in small model capabilities and local chip performance, this could be **completely viable in 1–2 years** — especially on-device.

### Status

So far, I’ve been working on:

- The API to load and query emails
- Draft generation
- Summarization

All done **locally**, using Ollama.



```bash
TEST_BACKEND=True fastapi run app.py --reload
```