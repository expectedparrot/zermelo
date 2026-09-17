"""Authored fictional candidate families and explicit variants; no model calls.

These are controlled concept cards, not descriptions of published books/films,
real proposals, or sampled people. Every family/variant pair is a distinct entrant.
"""


def rows(text):
    return [tuple(part.strip() for part in line.split('|')) for line in text.strip().splitlines()]


def profiles(text):
    return [{"name": name, "preferences": preferences} for name, preferences in rows(text)]


STUDIES = {
    "books": {
        "title": "Six readers walk into an imaginary bookstore",
        "feature": "Individual versus pooled rankings",
        "question": "Which original book concepts would six very different readers most want to read?",
        "criterion": "Rank these original book concepts by how much YOU would want to read the finished book, given your reading preferences. Assume equally competent execution, the same price, and no existing author reputation. Judge only the supplied concept. Put your most desired read FIRST.",
        "profiles": profiles('''
Mystery reader | Prefer fair clues, investigative puzzles, surprising but earned solutions, and a clear payoff.
Literary reader | Prefer nuanced relationships, moral ambiguity, interior life, and distinctive narrative voice.
Science reader | Prefer rigorous ideas, speculative discoveries, and thoughtful consequences of technology.
Adventure reader | Prefer exploration, momentum, unusual settings, and resourceful protagonists.
History reader | Prefer archives, social change, historical settings, and how ordinary lives intersect with institutions.
Comfort reader | Prefer warmth, humor, community, and hopeful endings rather than relentless danger.
'''),
        "families": rows('''
The Missing Atlas | A map restorer discovers that the same island has been erased from five unrelated atlases.
Letters at Low Tide | A coastal postal worker receives letters addressed to a village submerged a century ago.
The Last Orchard | Three siblings inherit an orchard whose aging keeper remembers a different family history.
A City That Listens | An acoustic engineer discovers that a city's traffic patterns encode a message.
The Borrowed Observatory | A rural teacher and her students restore an abandoned observatory and uncover its unfinished experiment.
The Night Train Ledger | A railway accountant finds impossible passenger counts on a discontinued night service.
Small Repairs | Neighbors who barely speak begin repairing one another's broken possessions in a shared courtyard.
The Glass Expedition | A botanist follows an extinct plant's trail through a chain of abandoned greenhouses.
A Dictionary of Departures | A translator catalogs words that refugees use for places they can no longer return to.
The Clockmaker's Summer | A retired clockmaker takes on an apprentice who refuses to measure time conventionally.
Under the Reservoir | A drought exposes a town's old streets and reopens an argument about why it was flooded.
The Second Weather | Meteorologists at an isolated station observe a forecast that only comes true indoors.
Three Seats at the Table | An estranged family must agree what to preserve when their neighborhood restaurant closes.
The Archive of Unfinished Things | A librarian acquires a collection of abandoned inventions and tries to complete one.
The Long Way to Tuesday | An exhausted courier finds that an unfamiliar delivery route keeps returning to the same day.
A House for Strangers | An innkeeper must decide which guests to trust when the only bridge washes away.
The Museum of Ordinary Work | A curator collects the tools of disappearing occupations while her own job is threatened.
Signals from the Garden | A community gardener notices that plants respond to broadcasts from an unused radio frequency.
The Weight of Paper | An apprentice printer becomes involved in a dispute over a secretly revised public document.
Beyond the Snow Road | Two travelers with incompatible accounts of the past guide a stranded convoy through a mountain pass.
'''),
        "variants": rows('''
Puzzle | Told as a tightly plotted mystery, with planted clues and an explicit final explanation.
Intimate | Told through close character portraits, unresolved loyalties, and a bittersweet emotional ending.
Speculative | Develops a carefully reasoned speculative mechanism and its social consequences.
Expedition | Emphasizes exploration, physical obstacles, brisk pacing, and an earned escape.
Warm | Emphasizes friendship, dry humor, mutual aid, and a hopeful resolution.
'''),
    },
    "features": {
        "title": "What should a shared-work app build next?",
        "feature": "Frozen ranker panels and adaptive follow-up comparisons",
        "question": "Which improvements matter most to different users of the same fictional work app?",
        "criterion": "Rank these proposed improvements to a fictional shared-work app by expected benefit to YOUR work, given your user profile. Assume equal subscription price, reliable implementation, and no implementation-cost differences. Rank user benefit, not engineering priority. Most beneficial FIRST.",
        "profiles": profiles('''
New user | Just joined a small team; need understandable defaults and help finding the next action.
Power user | Manage many projects daily; value speed, customization, keyboard access, and bulk operations.
Budget user | Work in a tiny organization; want useful basics without paying for extra services or spending setup time.
Administrator | Maintain a growing organization; prioritize permissions, auditability, consistency, and safe account management.
Collaborator | Coordinate work across teams and time zones; prioritize clear ownership, handoffs, and fewer interruptions.
Access-focused user | Use keyboard navigation and assistive technology; prioritize readable, predictable, accessible workflows.
'''),
        "families": rows('''
Task capture | Capture incoming requests and convert them into assigned tasks.
Search | Find relevant tasks, documents, comments, and decisions across projects.
Notifications | Manage updates so important changes reach the right person.
Project setup | Create a project with understandable milestones and ownership.
Progress view | See what is blocked, complete, or at risk across active work.
Permissions | Control who can view, comment on, and edit shared material.
Document history | Understand and recover earlier versions of shared documents.
Meeting follow-up | Convert meeting notes into explicit decisions and actions.
Workload view | Understand how tasks are distributed across team members.
Recurring work | Schedule repeated tasks without repeatedly rebuilding them.
Guest collaboration | Share a bounded piece of work with an external collaborator.
Data export | Retrieve project content in portable, reusable formats.
Offline work | Read and edit important material when the connection drops.
Onboarding | Help a new teammate understand projects, people, and expectations.
Templates | Reuse successful project structures without copying obsolete details.
Accessibility | Make navigation, forms, and status changes usable with assistive tools.
Time-zone handoffs | Communicate deadlines and responsibility across time zones.
Approval flow | Request a decision and see who still needs to respond.
Audit trail | Explain who changed important settings or project content and when.
Bulk cleanup | Archive, label, or reassign many outdated items at once.
'''),
        "variants": rows('''
Simple | A one-screen guided version with strong defaults and minimal setup; limited customization.
Flexible | A configurable version with filters, saved views, and reusable rules; requires setup.
Teamwide | A shared version with visible ownership and coordinated team workflows; adds team conventions.
Accessible | A keyboard-first, screen-reader-friendly version with plain language and adjustable display; fewer advanced controls.
'''),
    },
    "library": {
        "title": "One library, one hundred possible programs",
        "feature": "Ranker disagreement and explicit panel sensitivity",
        "question": "Does changing whose preferences count change the library's shortlist?",
        "criterion": "Rank these proposed public-library programs by how much YOU would want to attend, given your stated interests. Assume all are free, accessible, nearby, and offered at a time you can attend. Compare appeal rather than predicting attendance or social impact. Most appealing FIRST.",
        "profiles": profiles('''
Maker | Enjoy practical repairs, hands-on projects, and learning how everyday objects work.
Reader | Enjoy literature, thoughtful discussion, local stories, and quiet reflection.
Career learner | Want usable skills, confidence with technology, and opportunities to practice communicating.
Family visitor | Look for welcoming activities that adults and school-age children can enjoy together.
Community connector | Enjoy meeting neighbors, exchanging experiences, and collaborating across backgrounds.
Curious explorer | Want exposure to science, history, art, and unfamiliar ideas with little prior knowledge.
'''),
        "families": rows('''
Repair cafe | Diagnose and repair small everyday household objects with volunteers.
Language exchange | Practice everyday conversation with neighbors learning different languages.
Coding club | Build a tiny interactive program using beginner-friendly tools.
Quiet reading | Read personal book choices in a shared quiet space with an optional discussion.
Local history | Explore maps, photographs, and memories of the neighborhood.
Seed exchange | Share seeds and learn basic seasonal gardening techniques.
Story circle | Tell and listen to short personal stories about ordinary life.
Job interview practice | Rehearse interviews and exchange constructive feedback.
Digital confidence | Practice everyday computer tasks in a patient, supportive environment.
Board games | Learn and play approachable cooperative and competitive board games.
Book repair | Learn how to maintain and repair well-loved books.
Family science | Try simple hands-on science demonstrations with common materials.
Poetry lab | Read short poems aloud and draft an original poem.
Drawing from life | Practice observing and sketching everyday objects.
Oral history | Learn to record, describe, and preserve a family or community interview.
Music listening | Listen closely to selected music and discuss what different listeners notice.
Resume workshop | Improve the clarity and organization of a personal resume.
Community maps | Build a shared map of valued neighborhood places and resources.
Mending clothes | Practice visible mending and basic clothing repair.
Bird observation | Learn how to notice, sketch, and identify common local birds.
Writing letters | Write thoughtful personal letters and discuss memorable correspondence.
Photo storytelling | Arrange personal photographs to tell a short, coherent story.
Puzzle exchange | Solve and discuss logic, word, and spatial puzzles with others.
Public speaking | Practice a short talk with supportive audience feedback.
Library treasure hunt | Explore how to find unexpected materials and services in the library.
'''),
        "variants": rows('''
Intro session | One welcoming 60-minute introduction with no homework or ongoing commitment.
Four-week club | Four weekly 60-minute meetings with the same small group and gradual progression.
Drop-in lab | A flexible two-hour drop-in session where visitors work at their own pace.
Shared showcase | A 90-minute collaborative session ending with a low-pressure presentation of what participants made or learned.
'''),
    },
    "names": {
        "title": "Two hundred names for a tool that makes teamwork clearer",
        "feature": "Calibration across group sizes before production",
        "question": "How many names can judges compare before repeated preferences become inconsistent?",
        "criterion": "Rank these invented names for a fictional app that helps small teams turn scattered notes into clear shared plans. Prefer names that fit YOUR naming priorities. Assume identical functionality and pricing. Do not infer domain availability, trademark clearance, or an existing brand. Best name FIRST.",
        "profiles": profiles('''
Memorability | Value short, distinctive names that stick after one hearing.
Clarity | Want a name that suggests organization, shared plans, or useful direction.
Pronunciation | Prefer names that are easy to say, spell, and convey aloud.
Trust | Prefer calm, credible names suitable for a professional work tool.
Playfulness | Prefer friendly, inventive names with personality rather than corporate stiffness.
International use | Prefer simple letter patterns and few culture-specific idioms; do not assume universal linguistic suitability.
'''),
        "roots": "Clear Bright Team Plan Note Kind Open North True Calm Quick Shared Loom Cove Path Field Gather Signal Cedar Common".split(),
        "endings": "bridge nest lane light grove mark base flow craft point".split(),
    },
    "movies": {
        "title": "The movie-night problem, with films that do not exist yet",
        "feature": "Consensus versus polarizing favorites",
        "question": "Which original film pitches appeal across six different tastes?",
        "criterion": "Rank these original film pitches by how much YOU would want to watch them on a free evening. Assume each lasts 100 minutes, has equally competent acting and production, and costs the same. Use your stated taste and the supplied pitch, not imagined reviews. Most desired FIRST.",
        "profiles": profiles('''
Comedy fan | Prefer wit, warmth, amusing situations, and satisfying social resolutions.
Thriller fan | Prefer tension, clear stakes, smart reversals, and narrative momentum.
Character fan | Prefer psychologically believable people, relationships, and emotional complexity.
Worldbuilding fan | Prefer speculative rules, unfamiliar settings, and ideas that reward attention.
Adventure fan | Prefer exploration, physical action, teamwork, and resourceful problem solving.
Gentle viewer | Prefer hopeful stories and modest tension, avoiding bleakness and intense peril.
'''),
        "families": rows('''
Last Bus to Morning | Passengers on a stranded overnight bus must cooperate to get home.
The Spare Key | Neighbors discover that their spare keys open the same unoccupied apartment.
Small Town Signal | A community radio station receives a broadcast from its own future.
The Missing Guest | An event organizer must account for an important guest nobody remembers inviting.
A Better Map | Two estranged siblings follow a map drawn by their late grandfather.
One More Rehearsal | An amateur theater group has one night to replace its absent lead.
The Rooftop Garden | Residents try to save a shared garden from an unexpected building inspection.
The Final Delivery | A courier's last package leads to a place that does not appear on any map.
Under the Stage | A stagehand discovers an old room beneath a recently renovated concert hall.
The Perfect Substitute | A temporary worker is asked to impersonate an absent colleague at a crucial meeting.
A Week Without Screens | Friends retreat to a disconnected cabin and uncover an old disagreement.
The Borrowed Boat | A novice crew must return a borrowed boat before its owner comes home.
Everyone Knows the Song | People in a small town remember the same song but disagree about where it came from.
The Invisible Border | Residents find a line across their town that some people cannot cross.
The Last Table | A restaurant's final service brings together guests connected by an unknown event.
'''),
        "variants": rows('''
Comic | A warm ensemble comedy built around misunderstandings and an upbeat resolution.
Suspense | A tense thriller with escalating stakes, restrained violence, and a decisive twist.
Intimate | A character drama emphasizing difficult choices and an emotionally ambiguous ending.
Speculative | A science-fiction version with explicit unusual rules and consequences that follow from them.
Adventure | A fast-paced adventure emphasizing physical obstacles, ingenuity, and a hopeful escape.
'''),
    },
    "projects": {
        "title": "The best first programming project depends on the learner",
        "feature": "Separate projects for criterion sensitivity",
        "question": "Does the most motivating project also teach the most useful fundamentals?",
        "criterion": "Rank these beginner programming projects by how motivated YOU would be to start and finish them. Assume basic Python knowledge, free tools, and about ten hours available. Follow your stated interests; do not substitute a generic curriculum ranking. Most motivating FIRST.",
        "alternate_criterion": "Rank these beginner programming projects by how well they would help YOU learn reusable programming fundamentals: decomposition, data representation, control flow, testing, and debugging. Assume basic Python knowledge, free tools, and about ten hours available. Prioritize learning value over immediate entertainment. Best learning opportunity FIRST.",
        "profiles": profiles('''
Creative learner | Enjoy visual and musical outputs; want quick feedback and room for personal expression.
Practical learner | Want useful tools that improve everyday routines and remain useful after the exercise.
Game learner | Enjoy rules, feedback loops, playful challenges, and interactive experiences.
Data learner | Enjoy discovering patterns, making comparisons, and explaining results from small datasets.
Social learner | Want to build things to share with friends or support a club or community.
Careful learner | Prefer clear requirements, manageable scope, and explicit ways to check correctness.
'''),
        "families": rows('''
Habit journal | Record a daily habit and summarize streaks and gaps.
Tiny adventure | Build a short branching story with choices and multiple endings.
Playlist organizer | Tag a personal music list and create themed playlists.
Garden diary | Track planting dates, observations, and watering reminders.
Expense tracker | Categorize fictional transactions and summarize spending.
Flashcards | Quiz the learner on a personally chosen set of facts.
Recipe organizer | Store recipes and scale ingredient quantities.
Club planner | Record event ideas and find compatible meeting times.
Word puzzle | Create a small word-guessing game with hints.
Drawing machine | Generate geometric patterns from adjustable parameters.
Weather journal | Chart user-entered weather observations over time.
Book log | Track reading progress and summarize preferred genres.
Quiz night | Run a small multiple-choice quiz with team scores.
File organizer | Preview and safely reorganize a folder of sample files.
Practice timer | Manage focused practice intervals and record what was attempted.
Transit simulator | Model a fictional bus route and compare simple schedules.
Sound sequencer | Arrange short tones into a repeating musical pattern.
Sports notebook | Summarize a small fictional league's results and standings.
Study buddy | Match fictional students by availability and study topics.
Accessibility checker | Check a sample document for simple readability and formatting rules.
'''),
        "variants": rows('''
Terminal | A command-line version with clear text input, validation, and saved data.
Visual | A small local graphical version with immediate visual feedback and a few interactive controls.
Testable | A small reusable module plus tests, sample data, and a minimal demonstration interface.
'''),
    },
    "talks": {
        "title": "We ranked one hundred talks, then twenty more arrived",
        "feature": "Incremental entrants connected to preserved evidence",
        "question": "Can late proposals join a ranked pool without restarting the entire study?",
        "criterion": "Rank these fictional conference proposals by how much YOU would want to attend, given your professional interests. Assume equally capable speakers, accurate content, and 30-minute sessions. Rank individual appeal rather than designing an entire balanced schedule. Most desired FIRST.",
        "profiles": profiles('''
Researcher | Value precise questions, explicit assumptions, evaluation, and uncertainty.
Engineer | Value concrete implementation details, maintainability, and techniques usable at work.
Designer | Value understandable interfaces, user research, accessibility, and clear communication.
Team lead | Value coordination, prioritization, reliable delivery, and organizational learning.
New practitioner | Value approachable explanations, worked examples, and clear prerequisites.
Independent builder | Value low-cost tools, small deployments, autonomy, and practical tradeoffs.
'''),
        "families": rows('''
Reliable agents | Detect and recover from failures in a multistep software agent.
Small-data evaluation | Design useful evaluations when only a modest labeled sample exists.
Interfaces for uncertainty | Communicate uncertain results without overwhelming users.
Reproducible experiments | Preserve inputs, parameters, and artifacts across repeated experiments.
Accessible dashboards | Make complex status displays usable with different interaction needs.
Cost-aware inference | Estimate and track inference costs across a growing application.
Better code review | Structure reviews so teams find important defects and learn together.
Local-first tools | Build a useful application that keeps working without a network connection.
Data provenance | Track where data came from and which transformations produced an output.
Designing defaults | Choose defaults that help beginners while leaving room for experts.
Testing asynchronous work | Test queues, retries, timeouts, and partial completion reliably.
Useful documentation | Connect reference material, tutorials, and real task workflows.
Human feedback | Collect feedback that distinguishes preference from task correctness.
Small-team security | Improve everyday access control and secret handling in a small organization.
Choosing metrics | Avoid misleading success measures when goals have several dimensions.
Maintaining open source | Balance new features, support, release work, and contributor needs.
Scientific Python | Structure small research programs so others can inspect and reproduce them.
Operational handoffs | Transfer responsibility without losing context or creating ambiguity.
Debugging data pipelines | Find and localize silent errors in a chain of data transformations.
Model comparison | Compare alternative models while accounting for task and prompt variation.
Long-lived formats | Choose export formats and schemas that survive changing tools.
Search relevance | Evaluate whether a search tool returns what users actually need.
Responsible automation | Decide where a workflow benefits from automation and where review remains useful.
Learning from incidents | Turn a failure report into a specific, testable improvement.
'''),
        "variants": rows('''
Walkthrough | A beginner-friendly worked example, with prerequisites and each important decision explained.
Case study | A detailed account of one realistic project, including failure modes and tradeoffs.
Methods | A rigorous treatment of assumptions, measurement, and competing methodological choices.
Workshop | A hands-on session using a small reproducible exercise and take-home materials.
Debate | A structured comparison of two plausible approaches and the conditions favoring each.
'''),
    },
    "openings": {
        "title": "Which opening makes you turn the page?",
        "feature": "Task-cluster conditional sensitivity",
        "question": "Which leading openings remain near the top under whole-task reweighting?",
        "criterion": "Rank these original fictional opening paragraphs by how strongly YOU want to read the next page. Use your reader profile. Judge only the supplied prose, not an imagined complete novel. Most compelling FIRST.",
        "profiles": profiles('''
Suspense reader | Prefer immediate questions, plausible danger, and a clear reason to keep reading.
Voice reader | Prefer distinctive language, confident narration, and an interesting perspective.
Character reader | Prefer recognizable emotions, relationships, and consequential personal choices.
Humor reader | Prefer wit, playful expectations, and an inviting comic sensibility.
World reader | Prefer unusual settings or rules introduced through concrete details.
Clarity reader | Prefer understandable prose, a tangible situation, and a clear narrative foothold.
'''),
        "families": rows('''
The spare chair | Every evening, my father set a place for the person who had taken his job.
The wrong station | The train stopped at a station that had been demolished before I was born.
The inventory | The inventory listed twelve clocks, eleven chairs, and one unexplained apology.
The empty envelope | My sister mailed me an empty envelope every year, until the year it arrived heavy.
The borrowed voice | The first time the radio spoke in my voice, it pronounced my name correctly.
The new neighbor | Our new neighbor introduced herself by returning a cup we had not yet lent her.
The notice | The notice on the library door asked patrons to return any memories borrowed before June.
The morning shift | On my first morning as a lighthouse keeper, the sea was on the wrong side.
The last recipe | My grandmother's final recipe began with an instruction to forgive somebody.
The photograph | Everyone in the photograph was looking at the empty space where I should have stood.
The map | The map was accurate in every detail except the location of our house.
The rehearsal | We rehearsed the apology six times before anyone admitted what we had done.
The orchard | The orchard produced its first apples on the day we agreed to sell it.
The second bell | Nobody in the village remembered ordering the second church bell.
The package | The package was addressed to the person I had promised never to become.
The missing step | I had climbed those stairs for twenty years before I noticed the missing step.
The guest book | The inn's guest book contained my signature in three different centuries.
The final bus | The driver of the final bus asked whether I was going home or going back.
The silent room | The room had been silent for years, but somebody kept replacing the flowers.
The small mistake | The mistake was small enough to fit in a pocket and expensive enough to ruin us.
'''),
        "variants": rows('''
Confessional | I could explain what happened next, but not why I let it happen.
Comic | In our family, this qualified as an improvement.
Suspenseful | By the time I understood the warning, someone was already at the door.
Tender | For one brief moment, it felt as though we might begin again.
Strange | The only witness insisted that none of this had happened on a Tuesday.
'''),
    },
    "museum": {
        "title": "One set of ballots, three ranking methods",
        "feature": "Plackett–Luce, Bradley–Terry, and Elo on identical evidence",
        "question": "Where do ranking methods disagree about which exhibit concepts lead?",
        "criterion": "Rank these museum-exhibit concepts by how much YOU would want to visit them, given your interests. Assume equally competent execution, a one-hour visit, accessible displays, and identical ticket prices. Most appealing FIRST.",
        "profiles": profiles('''
Science visitor | Enjoy mechanisms, evidence, experiments, and discovering how the world works.
History visitor | Enjoy artifacts, changing societies, individual lives, and historical context.
Art visitor | Enjoy visual expression, materials, interpretation, and different creative perspectives.
Hands-on visitor | Prefer making, manipulating, and testing things rather than only reading.
Family visitor | Prefer activities that adults and school-age children can explore together.
Reflective visitor | Prefer thoughtful stories, quiet observation, and connections to everyday life.
'''),
        "families": rows('''
Deep ocean | Explore pressure, darkness, and adaptation in deep-sea environments.
Everyday inventions | Trace how ordinary objects were invented, revised, and adopted.
Night skies | Explore navigation, astronomy, and changing interpretations of the stars.
City water | Follow water through a fictional city's reservoirs, pipes, homes, and rivers.
Migration stories | Explore how people carry objects, ideas, and memories across places.
Color | Investigate pigments, perception, symbolism, and the making of color.
Timekeeping | Compare ways people measure, coordinate, and experience time.
Food journeys | Follow ingredients through farming, transport, kitchens, and shared meals.
Hidden sound | Explore vibration, hearing, acoustic spaces, and sound recording.
Repair | Examine how objects break and the skills used to keep them useful.
Maps and power | Explore what maps include, omit, and make possible.
Small worlds | Investigate miniature ecosystems and the organisms within them.
Textiles | Explore fibers, weaving, clothing, and the stories carried by fabric.
Play | Compare games, toys, rules, and the social uses of play.
Bridges | Explore how structures connect places and how engineers balance forces.
Letters | Follow personal correspondence through writing, transport, archives, and interpretation.
Weather | Explore observations, forecasting, and the experience of changing weather.
Workshops | Enter reconstructed spaces where people practice different skilled trades.
Light | Explore lenses, shadows, illumination, photography, and visual art.
Waste and reuse | Follow discarded objects through repair, recycling, and creative reuse.
'''),
        "variants": rows('''
Object gallery | A carefully interpreted collection of artifacts with concise labels and room for close looking.
Hands-on lab | Interactive stations where visitors manipulate materials and test simple explanations.
Human stories | A narrative exhibition following several people connected to the subject.
Immersive room | An atmospheric spatial experience using sound, projections, and large-scale visual displays.
'''),
    },
    "blog": {
        "title": "Can an agent finish its own ranking study?",
        "feature": "The next-command workflow, partial ingestion, and new entrants",
        "question": "Which article concepts would a technically curious audience most want to read?",
        "criterion": "Rank these proposed blog articles by how much YOU would want to read them, given your interests. Assume accurate, clearly written articles of equal length, freely available. Rank reader interest rather than predicted traffic. Most desired FIRST.",
        "profiles": profiles('''
Working developer | Want concrete techniques, usable examples, and honest implementation tradeoffs.
Research reader | Want clear assumptions, good experimental design, and careful interpretation.
Product builder | Want lessons about choosing useful work and understanding user differences.
Technical beginner | Want approachable explanations, modest prerequisites, and visible intermediate steps.
Skeptical reader | Want failure analysis, counterexamples, reproducible evidence, and limits on claims.
Curious generalist | Want an engaging question and a clear explanation that connects to familiar experience.
'''),
        "families": rows('''
Ranking without giant prompts | Compare many options through small overlapping groups.
What makes a useful agent | Examine the difference between executing commands and finishing a task.
The cost of a retry | Trace how failures and cache behavior affect the cost of an automated study.
When judges disagree | Distinguish repeat inconsistency from different underlying preferences.
Choosing the next experiment | Allocate additional comparisons after an initial set of results.
A reproducibility audit | Reconstruct an analysis from frozen inputs and preserved artifacts.
The danger of a single score | Explain what a pooled ranking hides about different audiences.
How defaults shape outcomes | Compare reasonable default settings and their consequences.
A small model comparison | Compare models on a narrow task with controlled inputs.
What uncertainty means here | Explain conditional sensitivity without claiming population accuracy.
A better command-line guide | Build workflow guidance that knows which prerequisites are missing.
Keeping credentials out of reports | Separate runnable artifacts from private account configuration.
Late-arriving candidates | Add new options to a ranking without discarding earlier comparisons.
The limits of synthetic users | Explore what authored personas can and cannot tell us.
A useful failed experiment | Show how a negative result changed the next question.
Tests for statistical software | Design recovery and invariance tests for ranking methods.
From notebook to package | Turn a one-off experiment into a reproducible command-line workflow.
One dataset, several methods | Compare different ranking models on identical observations.
Learning by building | Compare motivating projects with projects that teach reusable skills.
A museum of debugging | Explain common software failures through concrete, memorable examples.
The hidden work of datasets | Show how descriptions, IDs, and missing values shape an analysis.
Estimating before spending | Build a cost ledger before running external model calls.
A readable research report | Connect a central question, diagnostic figures, and preserved evidence.
When to stop collecting | Distinguish stability, precision, budget limits, and actual accuracy.
Revisiting a confident conclusion | Test whether an apparent winner survives a changed criterion.
'''),
        "variants": rows('''
Tutorial | A step-by-step worked example with runnable commands and small intermediate outputs.
Experiment | A controlled comparison with a clear question, prespecified analysis, and reported results.
Failure story | A narrative of something that went wrong, the diagnosis, and a concrete repair.
Visual explainer | A diagram-led explanation with a small interactive example and minimal prerequisites.
'''),
    },
}


def candidates(key):
    spec = STUDIES[key]
    if key == "names":
        pairs = [(root + ending, f"Candidate name: {root + ending}. A proposed name only; no existing brand is implied.")
                 for root in spec["roots"] for ending in spec["endings"]]
    else:
        pairs = [(f"{name} — {variant}", f"{description} {treatment}")
                 for name, description in spec["families"] for variant, treatment in spec["variants"]]
    return [{"id": f"{key}-{i:03d}", "name": name, "description": description}
            for i, (name, description) in enumerate(pairs, 1)]
