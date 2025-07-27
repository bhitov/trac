

## project selection

I originally wanted to try to modernize a COBOL project because I thought that would have been an interesting problem to work on, but unfortunately we couldn’t find any large open source COBOL projects. I’m guessing that is part of the reason why they are hard to fix. If you have enough people working on a problem in the open there tend to emerge common solutions for it

After that I tried a few other projects but had trouble getting them running. Projects that were old and had a compilation step were a pain to use with a new apple computer using the M4 apple silicon chip.

I tried trac for python and I was able to get it running in a few minutes! So that was my pick


## modernizing trac

I really appreciated how extensible trac was designed to be. I could incrementally modernize trac by plugging in to the existing framework. There was already a system set up for sending notifications by email that I could modify to include SMS and slack.

A pattern I relied on heavily for this project that I’d toyed with before but never gone all in on was test driven development (TDD)

### Spiky POV: TDD is terrible for humans but great for AI

I absolutely hated doing TDD when I was a regular software engineer. I assumed people who tried to push it were clueless. It slows down development to an unacceptable crawl and does not provide enough benefit over regular functional and integration testing to be worth the cost.

But for coding with AI it is awesome! LLMs are fantastic at pumping out tests. Test code is not usually very complicated but it has a lot of boilerplate and is so so boring to write for every possible edge case manually. Claude doesn’t get bored! Claude is happy to write 500 failing test cases in 15 minutes in a TDD pattern and then gradually get them to pass.

TDD guarantees your LLM has a view into whether or not your code is working. It is often a pain to get your agent to understand what the code actually succeeds in outputting, especially when you are testing web rendering. With TDD this was not (much of) a problem. I did still have to correct it a few times when it pretended to be rendering the frontend. Having direct feedback in claude’s programming loop greatly improves it’s performance in my experience.

—-

I did mostly feature additions because they were straightforward and offered clear value. The one major overhaul I did was migrating from python 3.12 to 3.13. It took the most time because it broke hundreds of tests that I had to update. But because of the feedback loop I described above, progress was steady.

## future work

I’d love to take on a large COBOL project if we find any. I think LLMs would handle it easily.

My plan would be something like… use LLMs to research existing technologies for mapping out COBOL projects. Have claude use them and keep track of places where they fail. Have claude inspect those cases one by one.

Build an interface layer between existing COBOL code and a modern language like rust. One section at at time, do… port tests to new language, port code to new language, connect ported code to old code with interface layer, test new code with new tests, get rid of old code.

