# Hackathon compass

A decision checklist for evaluating an idea, with the channel's own evidence attached to each stage. Work top to bottom. A stage you cannot answer is the stage to work on next — that is the point of the tool.

> ⚠️ **Generated with the offline heuristic engine, not an LLM.**
> Mechanisms and syntheses are placeholders. Set `LLM_API_KEY` and re-run
> `python run_pipeline.py --stage all` for real analysis.

<sub>Channel: `@demo_channel` · posts 43 · insights 16 · engines: heuristic</sub>

---


## How to use this

1. Write one sentence per question. If a sentence needs a hedge, mark the stage red.
2. Stop at the first red stage and fix it before building anything.
3. `python query.py "<your idea>" --critique` runs the same checklist against the knowledge base.


## Scorecard

| Stage | Question | Your answer | Red / amber / green |
|---|---|---|---|
| Problem | What real Job exists, and why is today's solution bad? | | |
| Segment | Who has this problem worse than everyone else? | | |
| Technology shift | What became possible only recently? | | |
| Value | What changes for the user — before → after? | | |
| Wedge | Which single narrow Job do you do dramatically better? | | |
| RAT | Which assumption kills the idea if it is false? | | |
| MVP | How do you test the RAT in 24-48 hours? | | |
| Distribution | Where are the first 10 users? | | |
| Demo | What can you show in 3 minutes so value is obvious? | | |


---

## Problem — What real Job exists, and why is today's solution bad?

- What Job is actually being hired for here — stated as a Job, not a feature?
- How do these people get it done today, including with a spreadsheet, a person, or nothing?
- Why is the current solution bad — mechanically, not adjectivally?
- What is the trigger that starts the Job?
- What are their criteria of success? How will they know it worked?

**What the channel says about this stage**

- **Сегментация по демографии не работает. Механизм простой: люди одного возраста и дохода решают разные Job в разных контекстах.**
  <br><sub>Механизм простой: люди одного возраста и дохода решают разные Job в разных контекстах. Демографический признак не предсказывает поведение, поэтому продукт, построенный на нём, оптимизируется под усреднённого пользователя. В результате ни один реальный сегмент не получает достаточной ценности, чтобы переключиться. Поэтому фокус — это не про дисциплину, это про арифметику.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1043](https://t.me/demo_channel/1043)</sub>
- **Про tax jobs. Есть Job, которые клиент выполняет не потому, что хочет, а потому, что их требует ваш продукт: заполнить профиль, настроить интеграцию, импортировать данные.**
  <br><sub>Механизм: каждый такой шаг отсеивает часть пользователей до момента, когда они увидели ценность. Поэтому активация растёт не от новых функций, а от снятия налога.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1015](https://t.me/demo_channel/1015)</sub>
- **Disruptive-продукт почти всегда сначала выглядит хуже. Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность.**
  <br><sub>Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность. Поэтому «наш продукт хуже, но дешевле» — это не оправдание, это иногда стратегия.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1010](https://t.me/demo_channel/1010)</sub>
- **Кейс. В проекте с маркетплейсом мы запустили эксперимент: убрали обязательную регистрацию до первого заказа.**
  <br><sub>Механизм: регистрация была tax job — она стояла до момента, когда клиент увидел ценность.</sub>
  <br><sub>`CASE_EVIDENCE` (strength 2/5) · [demo_channel/1030](https://t.me/demo_channel/1030)</sub>
- **Разберу, как искать wedge. Тред из трёх частей:**
  <br><sub>Механизм: переключение стоит клиенту денег, времени и риска, и маленькая разница этот барьер не окупает.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1037](https://t.me/demo_channel/1037) · [demo_channel/1038](https://t.me/demo_channel/1038) · [demo_channel/1039](https://t.me/demo_channel/1039) · [demo_channel/1040](https://t.me/demo_channel/1040)</sub>
- **Сейчас я бы сказал так: интервью — инструмент для поиска механизма, а не для валидации спроса. Спрос проверяется поведением: предоплатой, регистрацией, отказом от текущего решения.**
  <br><sub>Сейчас я бы сказал так: интервью — инструмент для поиска механизма, а не для валидации спроса.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1036](https://t.me/demo_channel/1036)</sub>

**Mistakes to avoid at this stage**

- **Самая частая ошибка в customer discovery — спрашивать про будущее. «Вы бы пользовались так** —  <br><sub>[demo_channel/1003](https://t.me/demo_channel/1003)</sub>


---

## Segment — Who has this problem worse than everyone else?

- Who feels this most acutely, and what makes them different from the average user?
- How often does the Job occur for them — daily, monthly, once a year?
- How painful is the current solution, in time or money they already spend?
- Can you find ten of them this week, by name of place or role?

**What the channel says about this stage**

- **Сегментация по демографии не работает. Механизм простой: люди одного возраста и дохода решают разные Job в разных контекстах.**
  <br><sub>Механизм простой: люди одного возраста и дохода решают разные Job в разных контекстах. Демографический признак не предсказывает поведение, поэтому продукт, построенный на нём, оптимизируется под усреднённого пользователя. В результате ни один реальный сегмент не получает достаточной ценности, чтобы переключиться. Поэтому фокус — это не про дисциплину, это про арифметику.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1043](https://t.me/demo_channel/1043)</sub>
- **Про tax jobs. Есть Job, которые клиент выполняет не потому, что хочет, а потому, что их требует ваш продукт: заполнить профиль, настроить интеграцию, импортировать данные.**
  <br><sub>Механизм: каждый такой шаг отсеивает часть пользователей до момента, когда они увидели ценность. Поэтому активация растёт не от новых функций, а от снятия налога.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1015](https://t.me/demo_channel/1015)</sub>
- **Disruptive-продукт почти всегда сначала выглядит хуже. Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность.**
  <br><sub>Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность. Поэтому «наш продукт хуже, но дешевле» — это не оправдание, это иногда стратегия.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1010](https://t.me/demo_channel/1010)</sub>
- **Ресурсы команды всегда ограничены. Если продукт одновременно оптимизируется под несколько сегментов с разными критериями успеха, разработка распределяется между несовместимыми требованиями.**
  <br><sub>Поэтому фокус — это не про дисциплину, это про арифметику.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1002](https://t.me/demo_channel/1002)</sub>
- **Кейс. В проекте с маркетплейсом мы запустили эксперимент: убрали обязательную регистрацию до первого заказа.**
  <br><sub>Механизм: регистрация была tax job — она стояла до момента, когда клиент увидел ценность.</sub>
  <br><sub>`CASE_EVIDENCE` (strength 2/5) · [demo_channel/1030](https://t.me/demo_channel/1030)</sub>
- **Разберу, как искать wedge. Тред из трёх частей:**
  <br><sub>Механизм: переключение стоит клиенту денег, времени и риска, и маленькая разница этот барьер не окупает.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1037](https://t.me/demo_channel/1037) · [demo_channel/1038](https://t.me/demo_channel/1038) · [demo_channel/1039](https://t.me/demo_channel/1039) · [demo_channel/1040](https://t.me/demo_channel/1040)</sub>


---

## Technology shift — What became possible only recently?

- What capability exists now that did not 18 months ago?
- Can the old Job now be done faster, cheaper, simpler, automatically, at higher quality, without an intermediary, or in fewer steps?
- Which of those is the one that actually changes the economics?
- What would falsify your belief that the constraint has moved?

**What the channel says about this stage**

- **Disruptive-продукт почти всегда сначала выглядит хуже. Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность.**
  <br><sub>Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность. Поэтому «наш продукт хуже, но дешевле» — это не оправдание, это иногда стратегия.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1010](https://t.me/demo_channel/1010)</sub>


---

## Value — What changes for the user — before → after?

- Write it as Before → After, in the user's terms. Never as 'we use AI agents'.
- What did the Before cost them in time, money, or risk?
- Would they notice the difference without being told?

**What the channel says about this stage**

- **Про tax jobs. Есть Job, которые клиент выполняет не потому, что хочет, а потому, что их требует ваш продукт: заполнить профиль, настроить интеграцию, импортировать данные.**
  <br><sub>Механизм: каждый такой шаг отсеивает часть пользователей до момента, когда они увидели ценность. Поэтому активация растёт не от новых функций, а от снятия налога.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1015](https://t.me/demo_channel/1015)</sub>
- **Disruptive-продукт почти всегда сначала выглядит хуже. Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность.**
  <br><sub>Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность. Поэтому «наш продукт хуже, но дешевле» — это не оправдание, это иногда стратегия.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1010](https://t.me/demo_channel/1010)</sub>
- **Ресурсы команды всегда ограничены. Если продукт одновременно оптимизируется под несколько сегментов с разными критериями успеха, разработка распределяется между несовместимыми требованиями.**
  <br><sub>Поэтому фокус — это не про дисциплину, это про арифметику.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1002](https://t.me/demo_channel/1002)</sub>
- **Разберу, как искать wedge. Тред из трёх частей:**
  <br><sub>Механизм: переключение стоит клиенту денег, времени и риска, и маленькая разница этот барьер не окупает.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1037](https://t.me/demo_channel/1037) · [demo_channel/1038](https://t.me/demo_channel/1038) · [demo_channel/1039](https://t.me/demo_channel/1039) · [demo_channel/1040](https://t.me/demo_channel/1040)</sub>
- **Про MVP. MVP — не маленькая версия продукта.**
  <br><sub>Если RAT про спрос, то код вообще не нужен: нужна страница, письмо и десять разговоров. Механизм ошибки: команда путает «минимальный продукт» с «минимальным экспериментом» и тратит четыре недели там, где хватило бы двух дней.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1005](https://t.me/demo_channel/1005)</sub>
- **Кейс. В проекте с маркетплейсом мы запустили эксперимент: убрали обязательную регистрацию до первого заказа.**
  <br><sub>Механизм: регистрация была tax job — она стояла до момента, когда клиент увидел ценность.</sub>
  <br><sub>`CASE_EVIDENCE` (strength 2/5) · [demo_channel/1030](https://t.me/demo_channel/1030)</sub>

**Mistakes to avoid at this stage**

- **Сегментация по демографии не работает. Механизм простой: люди одного возраста и дохода реш** —  <br><sub>[demo_channel/1001](https://t.me/demo_channel/1001)</sub>


---

## Wedge — Which single narrow Job do you do dramatically better?

- Which one Job can you be 10x on, rather than 10% on across five?
- What are you explicitly NOT doing in v1?
- What does winning that wedge give you access to next?

**What the channel says about this stage**

- **Сегментация по демографии не работает. Механизм простой: люди одного возраста и дохода решают разные Job в разных контекстах.**
  <br><sub>Механизм простой: люди одного возраста и дохода решают разные Job в разных контекстах. Демографический признак не предсказывает поведение, поэтому продукт, построенный на нём, оптимизируется под усреднённого пользователя. В результате ни один реальный сегмент не получает достаточной ценности, чтобы переключиться. Поэтому фокус — это не про дисциплину, это про арифметику.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1043](https://t.me/demo_channel/1043)</sub>
- **Ресурсы команды всегда ограничены. Если продукт одновременно оптимизируется под несколько сегментов с разными критериями успеха, разработка распределяется между несовместимыми требованиями.**
  <br><sub>Поэтому фокус — это не про дисциплину, это про арифметику.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1002](https://t.me/demo_channel/1002)</sub>
- **Disruptive-продукт почти всегда сначала выглядит хуже. Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность.**
  <br><sub>Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность. Поэтому «наш продукт хуже, но дешевле» — это не оправдание, это иногда стратегия.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1010](https://t.me/demo_channel/1010)</sub>


---

## RAT — Which assumption kills the idea if it is false?

- List the assumptions. Which single one, if false, makes everything else irrelevant?
- Is it a demand assumption, a technical assumption, or a distribution assumption?
- What observation would falsify it? If you cannot state one, it is not a RAT.

**What the channel says about this stage**

- **Сегментация по демографии не работает. Механизм простой: люди одного возраста и дохода решают разные Job в разных контекстах.**
  <br><sub>Механизм простой: люди одного возраста и дохода решают разные Job в разных контекстах. Демографический признак не предсказывает поведение, поэтому продукт, построенный на нём, оптимизируется под усреднённого пользователя. В результате ни один реальный сегмент не получает достаточной ценности, чтобы переключиться. Поэтому фокус — это не про дисциплину, это про арифметику.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1043](https://t.me/demo_channel/1043)</sub>
- **Кейс. В проекте с маркетплейсом мы запустили эксперимент: убрали обязательную регистрацию до первого заказа.**
  <br><sub>Механизм: регистрация была tax job — она стояла до момента, когда клиент увидел ценность.</sub>
  <br><sub>`CASE_EVIDENCE` (strength 2/5) · [demo_channel/1030](https://t.me/demo_channel/1030)</sub>
- **Про MVP. MVP — не маленькая версия продукта.**
  <br><sub>Если RAT про спрос, то код вообще не нужен: нужна страница, письмо и десять разговоров. Механизм ошибки: команда путает «минимальный продукт» с «минимальным экспериментом» и тратит четыре недели там, где хватило бы двух дней.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1005](https://t.me/demo_channel/1005)</sub>


---

## MVP — How do you test the RAT in 24-48 hours?

- What is the cheapest artefact that produces a real signal — not a nicer opinion?
- Can the test run without building the product at all?
- What result would make you stop?

**What the channel says about this stage**

- **Сегментация по демографии не работает. Механизм простой: люди одного возраста и дохода решают разные Job в разных контекстах.**
  <br><sub>Механизм простой: люди одного возраста и дохода решают разные Job в разных контекстах. Демографический признак не предсказывает поведение, поэтому продукт, построенный на нём, оптимизируется под усреднённого пользователя. В результате ни один реальный сегмент не получает достаточной ценности, чтобы переключиться. Поэтому фокус — это не про дисциплину, это про арифметику.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1043](https://t.me/demo_channel/1043)</sub>
- **Про tax jobs. Есть Job, которые клиент выполняет не потому, что хочет, а потому, что их требует ваш продукт: заполнить профиль, настроить интеграцию, импортировать данные.**
  <br><sub>Механизм: каждый такой шаг отсеивает часть пользователей до момента, когда они увидели ценность. Поэтому активация растёт не от новых функций, а от снятия налога.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1015](https://t.me/demo_channel/1015)</sub>
- **Disruptive-продукт почти всегда сначала выглядит хуже. Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность.**
  <br><sub>Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность. Поэтому «наш продукт хуже, но дешевле» — это не оправдание, это иногда стратегия.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1010](https://t.me/demo_channel/1010)</sub>
- **Ресурсы команды всегда ограничены. Если продукт одновременно оптимизируется под несколько сегментов с разными критериями успеха, разработка распределяется между несовместимыми требованиями.**
  <br><sub>Поэтому фокус — это не про дисциплину, это про арифметику.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1002](https://t.me/demo_channel/1002)</sub>
- **Кейс. В проекте с маркетплейсом мы запустили эксперимент: убрали обязательную регистрацию до первого заказа.**
  <br><sub>Механизм: регистрация была tax job — она стояла до момента, когда клиент увидел ценность.</sub>
  <br><sub>`CASE_EVIDENCE` (strength 2/5) · [demo_channel/1030](https://t.me/demo_channel/1030)</sub>
- **Про MVP. MVP — не маленькая версия продукта.**
  <br><sub>Если RAT про спрос, то код вообще не нужен: нужна страница, письмо и десять разговоров. Механизм ошибки: команда путает «минимальный продукт» с «минимальным экспериментом» и тратит четыре недели там, где хватило бы двух дней.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1005](https://t.me/demo_channel/1005)</sub>


---

## Distribution — Where are the first 10 users?

- Name the specific place: a community, a Slack, a queue, a physical location.
- What is your reason to be there that is not 'we are launching a product'?
- What is the single message that would make one of them reply?

**What the channel says about this stage**

- **Про tax jobs. Есть Job, которые клиент выполняет не потому, что хочет, а потому, что их требует ваш продукт: заполнить профиль, настроить интеграцию, импортировать данные.**
  <br><sub>Механизм: каждый такой шаг отсеивает часть пользователей до момента, когда они увидели ценность. Поэтому активация растёт не от новых функций, а от снятия налога.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1015](https://t.me/demo_channel/1015)</sub>
- **Кейс. В проекте с маркетплейсом мы запустили эксперимент: убрали обязательную регистрацию до первого заказа.**
  <br><sub>Механизм: регистрация была tax job — она стояла до момента, когда клиент увидел ценность.</sub>
  <br><sub>`CASE_EVIDENCE` (strength 2/5) · [demo_channel/1030](https://t.me/demo_channel/1030)</sub>
- **Дистрибуция — часть продукта, а не то, что делают после. Механизм: канал определяет, какой сегмент вы получите, а сегмент определяет, какую Job вы должны выполнять.**
  <br><sub>Механизм: канал определяет, какой сегмент вы получите, а сегмент определяет, какую Job вы должны выполнять.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1007](https://t.me/demo_channel/1007)</sub>


---

## Demo — What can you show in 3 minutes so value is obvious?

- What is the one moment on stage where the audience gets it without explanation?
- Can you show the Before as well as the After?
- What are you cutting so the demo fits in three minutes?

**What the channel says about this stage**

- **Про tax jobs. Есть Job, которые клиент выполняет не потому, что хочет, а потому, что их требует ваш продукт: заполнить профиль, настроить интеграцию, импортировать данные.**
  <br><sub>Механизм: каждый такой шаг отсеивает часть пользователей до момента, когда они увидели ценность. Поэтому активация растёт не от новых функций, а от снятия налога.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1015](https://t.me/demo_channel/1015)</sub>
- **Disruptive-продукт почти всегда сначала выглядит хуже. Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность.**
  <br><sub>Механизм: он выигрывает по измерению, которое существующий рынок не считает важным — цена, скорость, доступность. Поэтому «наш продукт хуже, но дешевле» — это не оправдание, это иногда стратегия.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1010](https://t.me/demo_channel/1010)</sub>
- **Ресурсы команды всегда ограничены. Если продукт одновременно оптимизируется под несколько сегментов с разными критериями успеха, разработка распределяется между несовместимыми требованиями.**
  <br><sub>Поэтому фокус — это не про дисциплину, это про арифметику.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1002](https://t.me/demo_channel/1002)</sub>
- **Разберу, как искать wedge. Тред из трёх частей:**
  <br><sub>Механизм: переключение стоит клиенту денег, времени и риска, и маленькая разница этот барьер не окупает.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1037](https://t.me/demo_channel/1037) · [demo_channel/1038](https://t.me/demo_channel/1038) · [demo_channel/1039](https://t.me/demo_channel/1039) · [demo_channel/1040](https://t.me/demo_channel/1040)</sub>
- **Про MVP. MVP — не маленькая версия продукта.**
  <br><sub>Если RAT про спрос, то код вообще не нужен: нужна страница, письмо и десять разговоров. Механизм ошибки: команда путает «минимальный продукт» с «минимальным экспериментом» и тратит четыре недели там, где хватило бы двух дней.</sub>
  <br><sub>`AUTHOR_CLAIM` (strength 1/5) ⚠️ _unsupported in the material_ · [demo_channel/1005](https://t.me/demo_channel/1005)</sub>
- **Кейс. В проекте с маркетплейсом мы запустили эксперимент: убрали обязательную регистрацию до первого заказа.**
  <br><sub>Механизм: регистрация была tax job — она стояла до момента, когда клиент увидел ценность.</sub>
  <br><sub>`CASE_EVIDENCE` (strength 2/5) · [demo_channel/1030](https://t.me/demo_channel/1030)</sub>

**Mistakes to avoid at this stage**

- **Сегментация по демографии не работает. Механизм простой: люди одного возраста и дохода реш** —  <br><sub>[demo_channel/1001](https://t.me/demo_channel/1001)</sub>
