# AI LLM Market Intelligence Platform

## Complete Project Handoff Specification (v1)

---

# Project Name

**PulseAI** *(working title)*

Alternative names:

* LLM Pulse
* ModelScope
* Sentient
* ModelWatch
* Cortex Signals
* OpenBench
* Model Intelligence
* LLM Radar

---

# Vision

Build the definitive real-time intelligence platform for Large Language Models.

Instead of benchmarking models using static evaluations, this platform measures **public perception, developer adoption, feature reception, market momentum, and competitive positioning** across the internet.

Think of it as:

> Bloomberg Terminal + Brandwatch + SimilarWeb + GitHub Trends + Google Trends, specifically for AI models.

The platform continuously ingests millions of public signals and transforms them into structured market intelligence.

---

# Primary Goals

The platform should answer questions like:

* Why are developers switching from ChatGPT to Claude?
* Which model has the fastest growing momentum?
* Which releases were received positively?
* What features are people asking for?
* Which AI companies are being criticized?
* Which model is considered best for coding today?
* Which model has the highest recommendation rate?
* Which bugs are frustrating users?
* Which AI startup is gaining traction?
* What trends are emerging before they become mainstream?

---

# Models To Track

Initial

OpenAI

* ChatGPT
* GPT-5
* GPT-5 Nano
* GPT-5 Mini
* Codex

Anthropic

* Claude
* Claude Code
* Claude Sonnet
* Claude Opus
* Claude Haiku

Google

* Gemini
* Gemini CLI
* Gemini Pro
* Gemini Flash
* Deep Research

xAI

* Grok

Meta

* Llama

Mistral

* Mistral
* Le Chat

DeepSeek

Perplexity

Microsoft

* Copilot

Amazon

* Nova

Cohere

Qwen

Kimi

Open Source

* Ollama
* LM Studio
* vLLM
* llama.cpp

Future models should be configurable through a database rather than hardcoded.

---

# Data Sources

## Reddit

Collect

* Posts
* Comments
* Votes
* Awards
* Crossposts
* Flair
* Timestamp

Subreddits

r/ChatGPT

r/OpenAI

r/ClaudeAI

r/Anthropic

r/GeminiAI

r/LocalLLaMA

r/MachineLearning

r/singularity

r/Artificial

r/PromptEngineering

r/LLM

r/Grok

r/StableDiffusion

r/Programming

r/Python

r/ExperiencedDevs

---

## Hacker News

Collect

* Stories
* Comments
* Points
* Rank
* Author
* Timestamp

---

## GitHub

Collect

Repositories

Issues

Pull Requests

Discussions

Releases

README mentions

Stars

Forks

Trending repositories

---

## YouTube

Collect

Videos

Titles

Descriptions

Comments

Likes

Views

Transcripts (where available)

---

## X

Collect

Posts

Replies

Likes

Reposts

Bookmarks (if available)

Views

---

## News

Collect RSS + APIs

Reuters

The Verge

TechCrunch

Ars Technica

VentureBeat

MIT Technology Review

OpenAI Blog

Anthropic Blog

Google AI Blog

Microsoft Blog

Meta AI Blog

---

## Product Hunt

Launches

Reviews

Comments

---

## StackOverflow

Questions

Answers

Votes

Tags

---

## App Store

ChatGPT

Claude

Gemini

Perplexity

Grok

---

## Google Trends

Search popularity

---

## Optional Later

Discord

Bluesky

Mastodon

LinkedIn

TikTok

Dev.to

Medium

---

# Data Pipeline

```
Collectors
        │
        ▼

Queue (Redis Streams)

        ▼

Normalizer

        ▼

Entity Detection

        ▼

Deduplication

        ▼

Embedding Generation

        ▼

Classification

        ▼

Sentiment

        ▼

Storage

        ▼

Analytics

        ▼

Dashboard
```

---

# Tech Stack

Backend

Python

FastAPI

Pydantic

SQLAlchemy

Alembic

AsyncIO

httpx

Redis Streams

PostgreSQL

pgvector

Celery (optional)

Frontend

Next.js

TypeScript

Tailwind

shadcn/ui

ECharts

React Query

Backend AI

OpenAI

Anthropic

Sentence Transformers

bge-large

spaCy

Deployment

Docker

Docker Compose

GitHub Actions

Cloudflare

Railway/Fly.io

S3 compatible storage

---

# Database Schema

## Models

```
id
name
company
aliases
website
active
```

---

## Sources

```
id
name
type
priority
enabled
```

---

## Documents

```
id
source
url
author
title
content
timestamp
language
score
views
likes
shares
comments
raw_json
```

---

## Mentions

```
id
document_id
model_id
confidence
position
```

---

## Sentiment

```
id
document_id
model_id
positive
negative
neutral
confidence
```

---

## Topics

```
id
name
```

Examples

Coding

Writing

Agents

API

Pricing

Hallucinations

Reasoning

Context Window

Vision

Speed

Latency

Voice

Safety

Enterprise

Education

---

## Document Topics

```
document_id
topic_id
confidence
```

---

## Comparisons

```
document_id
winner
loser
confidence
```

---

## Releases

```
company
model
version
date
summary
```

---

## Embeddings

```
document_id
embedding
```

pgvector

---

# NLP Pipeline

Every document goes through

```
Language Detection

↓

Spam Detection

↓

Entity Recognition

↓

Model Identification

↓

Embedding

↓

Topic Classification

↓

Intent Classification

↓

Sentiment

↓

Comparison Extraction

↓

Feature Extraction

↓

Storage
```

---

# Topic Classification

Documents can have multiple labels.

Examples

Coding

Writing

Reasoning

Math

Search

Research

API

Pricing

Enterprise

Vision

Audio

Voice

Mobile

Desktop

Agents

Image Generation

Long Context

Tool Use

Memory

Hallucination

Latency

Speed

Benchmark

Safety

Privacy

Fine-tuning

Open Source

---

# Intent Classification

Instead of only sentiment

Predict

Praise

Complaint

Recommendation

Question

Feature Request

Bug Report

Migration

Comparison

Tutorial

News

Release Discussion

Benchmark

Opinion

Showcase

Meme

---

# Sentiment

Store

Overall

Aspect sentiment

Examples

Claude

Positive

Coding

Positive

Pricing

Negative

API

Neutral

---

# Pairwise Comparison Detection

Detect statements like

Claude > GPT

GPT better than Gemini

Switched from Claude to Gemini

Moved from ChatGPT

Extract

Winner

Loser

Confidence

Reason

---

# Feature Extraction

Automatically identify

Price

Latency

Memory

Tool Calling

Reasoning

Context Window

Code Quality

Creativity

Search

Agents

Voice

Images

Desktop App

CLI

MCP

---

# Trend Detection

Hourly

Daily

Weekly

Monthly

Compute

Fastest growing model

Largest sentiment increase

Largest sentiment decrease

Most discussed topic

Most controversial release

Highest recommendation rate

Highest complaint rate

Biggest migration

Most viral discussion

---

# Analytics

Momentum Score

Mindshare

Developer Love

Consumer Love

Enterprise Adoption

Recommendation Rate

Complaint Rate

Release Success

Trust Score

Innovation Score

Community Growth

Search Interest

GitHub Activity

News Volume

---

# Dashboard Pages

## Home

Overall market overview

---

## Models

Each model gets

Timeline

Sentiment

Mentions

Growth

Top complaints

Top praise

Top comparisons

---

## Companies

OpenAI

Anthropic

Google

Meta

xAI

DeepSeek

etc.

---

## Compare

ChatGPT vs Claude

Gemini vs Grok

DeepSeek vs GPT

Interactive charts

---

## Topics

Coding

Reasoning

Vision

Pricing

API

Track trends

---

## Releases

Timeline of releases

Sentiment before/after

---

## News

Aggregated news

Importance score

---

## Reddit

Trending discussions

---

## GitHub

Trending repositories

Most mentioned projects

---

## Daily Report

Automatically generated.

Example

```
Today

Claude Code sentiment increased 17%

ChatGPT complaints centered around pricing

Gemini adoption increased in enterprise discussions

DeepSeek mentions doubled after benchmark release

Top complaint:
Rate limits

Top praise:
Coding quality

Top comparison:
Claude surpassed GPT in coding discussions
```

---

# AI Reports

Every morning generate

Executive Summary

Developer Summary

Investor Summary

Open Source Summary

News Summary

Enterprise Summary

Weekly Reports

Monthly Reports

---

# Search

Semantic search

Examples

"People complaining about GPT pricing"

"Claude coding praise"

"Gemini hallucinations"

"OpenAI enterprise"

Vector search using pgvector.

---

# Alert System

Examples

Notify if

Claude sentiment changes >15%

Model mentions double

Major release detected

Breaking news

Large migration detected

GitHub stars spike

News sentiment drops

---

# API

REST

Future GraphQL

Endpoints

```
/models

/sentiment

/trends

/mentions

/search

/reports

/compare

/releases

/news
```

---

# Future Features

AI-generated podcasts summarizing weekly trends

Interactive timelines

Knowledge graph of AI ecosystem

Market prediction model

Stock correlation analysis

Open-source ecosystem ranking

GitHub dependency analysis

Influencer tracking

Conference monitoring

Research paper tracking

Patent tracking

AI benchmark ingestion

Live release monitoring

Email newsletter generation

Slack integration

Discord bot

Browser extension

Mobile app

---

# Long-Term Vision

This platform should become the canonical source for understanding the AI ecosystem in real time.

It should answer not only **"What are people saying?"** but also:

* Why did sentiment change?
* Which events caused it?
* What features matter most?
* Which communities drive adoption?
* Which companies are gaining or losing trust?
* Which models dominate specific use cases?
* What trends are likely to emerge next?

The end goal is an intelligence platform that transforms billions of unstructured online conversations into actionable, searchable, and explainable market insights for developers, researchers, investors, journalists, and AI companies.
