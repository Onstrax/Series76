## Stack
Python FastAPI, PostgreSQL (pgvector extension?), Develop VScode, Emulate Android Studio, Kotlin with Jetpack Compose
To start, set-up de Google AI studio
Mono repo for python backend-db and kotlin app. Docker compose. Use Android Studio to emulate

## Useful prioritary
MCP?, RAG, Memory, Evals, re-prompting, caching, queues, local storage, fetching strategies, multithreading, SDD
## Useful Complementary
Domain Specific tokenization for chunks in RAG, PostQuantum Criptograpgy ML-KEM, ML-DSA and SHA256, accesibility, eventual connectivity,

## Breaking down the problem
1) Define all posible aspects a user could ask (user stories or use cases (funtional, use INVEST principle) and Architecture Quality Attribute Scenarios (non-funtional))
2) Define DB schema (all tables and their columns)
3) Parse Data (ETL)
4) Define all contracts
5) Define all endpoints
6) Define custom LangChain tool
7) Define Screens (dev)
8) Populate DB (ingest and mock users)
9) Build API
10) Build App
11) Integrate both
12) Test

## Discuss
Retrival using RAG? What other options are there?
How to parse pdf to sql? I thing is an image and not readable data. What existing tools could I use?
What are all the tasks that may require a LLM? Which LLM fits best echa task cost-efficiently?
If decided to use a RAG, what posible models use to tokenize? Worth fine-tunning (probably yes)?
How to test edge cases (invalid numbers, missing data, ambiguos queries, prompt injection, hijacking and jailbreaking)
What other fields might the API contract benefit from? For example for clear visualizations (tables? diagrams?)
Where to put developer screen? thinking no new screen, just a modal with extra details when clicking a message inside a chat screen (so all messages must store in DB the tools, paremeters used and data returned, but only send them when requested by an admin)
Discuss all posible design patterns (factory, observer, facade, DAO, DTO, MVC MVVM, etc) architectural styles (data flow, call return, repo, event based, etc) and decisions and software tactics. 

## Domain
Electric actuators, users, conversations/history/sessionId, recomendations? (probably not), LLM ENUM?, messages, context?, tools called (ENUM?), parameters used in call

## Generalities
Full traceability (document whole process from first toughts, design, decisions, building, changes, testing, results, etc) 
Do login from beggining, harder to add later
Voice can be added with remaining time (try local, avoid using openrouter key)
Every decision must have a rationele
Never let LLM take decitions on it's own, always validate with me
Always challenge my thinking until a decision is taken, state out loud my good calls and also mistakes; always propose other alternatives with their advantages and disadvantages
Nothing can be implemented before green light. Green light is only stated once 100% everything was contemplated, justificated and there is no ambuguity or clear better option
In the beggining we must state clear phases to defin project progress (not too many, not too few)