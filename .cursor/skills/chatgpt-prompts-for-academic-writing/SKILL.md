---
name: chatgpt-prompts-for-academic-writing
description: Provide reusable prompts for academic writing tasks including brainstorming, section drafting, language polishing, summarization, and research planning. Use when the user asks for论文写作提示词、学术英文润色、文献综述、摘要改写、研究计划、参考文献格式转换或相关学术写作支持.
---

# ChatGPT Prompts for Academic Writing

## Purpose

Turn rough research intent into high-quality prompts for academic writing with minimal back-and-forth.

## Workflow

1. Identify the exact writing task (brainstorming, section drafting, language improvement, summarization, planning).
2. Ask for missing inputs only if essential (topic, paragraph, target journal/style, word limit, language).
3. Return:
   - one **directly usable prompt** (default),
   - plus 2 optional variants only if the user asks for alternatives.
4. If references are requested, add a hallucination warning and require source verification.

## Prompt Construction Rules

- Keep placeholders explicit: `[TOPIC]`, `[PARAGRAPH]`, `[RESEARCH_DOMAIN]`, `[WORD_COUNT]`.
- Prefer one clear instruction over multi-objective prompts.
- Include format constraints only when needed (APA/Harvard, bullet list, table, exact word count).
- For long inputs, allow chunking:
  - `Read this paragraph: [PARAGRAPH_CHUNK]`
  - Final prompt: `Considering all previous chunks, ...`

## Safety and Quality Checks

- Never present generated citations as verified facts.
- Add this note when references are involved:
  - `请逐条核验文献的标题、作者、年份、DOI/链接，避免虚构引用。`
- If user asks for plagiarism-free text, frame as:
  - original writing + proper citation + manual verification.

## Prompt Library

### 1) Brainstorming

- `Find a research topic for a PhD in the area of [TOPIC].`
- `Identify gaps in the literature on [TOPIC].`
- `Generate 10 academic research questions about [TOPIC].`
- `Suggest novel applications of [TOPIC] within [RESEARCH_DOMAIN].`

### 2) Article Sections

- **Title**: `Suggest 5 titles for the following abstract: [ABSTRACT].`
- **Abstract**: `Generate an abstract for a scientific paper based on: [PARAGRAPH].`
- **Introduction**: `Write an introduction for the research topic: [TOPIC].`
- **Methodology**: `Write a detailed methodology for: [TOPIC].`
- **Results**: `Write a result section in third person based on: [PARAGRAPHS].`
- **Discussion**: `Discuss these results: [RESULT_PARAGRAPHS].`
- **Conclusion**: `Generate a conclusion for: [PARAGRAPHS].`

### 3) Literature Review and References

- `Conduct a literature review on [TOPIC] and provide references.`
- `Summarize the scholarly literature with in-text citations on [TOPIC].`
- `Convert this bibliography from MLA to APA: [BIBLIOGRAPHY].`
- `Write this in Harvard referencing style: [PARAGRAPH].`

Use with verification note for all reference-related outputs.

### 4) Language Improvement

- `Rewrite this paragraph in academic language: [PARAGRAPH].`
- `Paraphrase with scientific tone, neutral voice, and no repetition: [PARAGRAPH].`
- `Correct grammar and punctuation: [PARAGRAPH].`
- `Improve clarity and coherence: [PARAGRAPHS].`
- `Provide 3 concrete improvements for this paragraph: [PARAGRAPH].`

### 5) Summarization

- `Summarize the following content: [PARAGRAPHS].`
- `Summarize in exactly [WORD_COUNT] words: [PARAGRAPHS].`
- `Give a bullet-point summary for: [PARAGRAPHS].`
- `Explain this research to a 12-year-old: [PARAGRAPHS].`

### 6) Planning and Communication

- `Develop a research plan for: [TOPIC].`
- `Create a week-by-week writing schedule until [DATE].`
- `Write 3 tweets about this research: [PARAGRAPHS].`
- `Write a press release for this research: [PARAGRAPHS].`

## Output Style

When user asks for "给我提示词", default output format:

```markdown
任务: <一句话定义任务>
可直接复制的提示词:
<prompt>

可选参数:
- 语气/风格: ...
- 长度限制: ...
- 引用格式: ...
```

When user provides raw text, default to one refined prompt plus a short "how to use" note.

## Source

This skill is adapted from the prompt collection in:
- `.claude/skills/chatgpt-prompts-for-academic-writing/README.md`
