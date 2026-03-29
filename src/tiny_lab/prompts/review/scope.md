You are defining the scope for a systematic literature review.

Current iteration: {iter}

## Your Task

Define clear research questions and screening criteria for the review.

Read research/.user_idea.txt if it exists for the user's review topic.

## Step 1: Define research questions

Formulate 2-4 specific research questions. Each should be:

- Answerable by surveying existing literature
- Specific enough to guide paper selection
- Broad enough to capture relevant work

## Step 2: Define inclusion/exclusion criteria

Inclusion criteria: what makes a paper relevant?

- Publication year range
- Venue types (journals, conferences, preprints)
- Methodology types
- Domain constraints

Exclusion criteria: what disqualifies a paper?

- Language, access, quality thresholds

## Output

Write to research/{iter}/.scope.json:

- research_questions: list of questions
- inclusion_criteria: list of criteria
- exclusion_criteria: list of criteria
- search_terms: suggested search queries
- expected_paper_count: rough estimate
