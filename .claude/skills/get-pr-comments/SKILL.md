---
name: get-pr-comments
description: Fetches PR review comments for the current branch using gh CLI
---

# Get PR Comments

Fetch and display review comments from the GitHub PR associated with the current branch.

## Instructions

1. Get the current git branch:
   ```bash
   git branch --show-current
   ```

2. Find the PR associated with this branch:
   ```bash
   gh pr list --head <branch-name> --json number,url --jq '.[0]'
   ```

3. If a PR exists, fetch the review threads using GraphQL to get the resolved status:
   ```bash
   gh api graphql -f query='
   query($owner:String!, $repo:String!, $pr:Int!) {
     repository(owner:$owner, name:$repo) {
       pullRequest(number:$pr) {
         reviewThreads(first:100) {
           nodes {
             isResolved
             comments(first:10) {
               nodes {
                 body
                 path
                 author { login }
               }
             }
           }
         }
       }
     }
   }' -f owner=OWNER -F pr=PR_NUMBER -f repo=REPO
   ```

4. Present the comments as a markdown table with these columns:
   - **Filename** - The file where the comment was made
   - **Comment** - The comment body
   - **Author** - Who wrote the comment
   - **Resolved** - Whether the review thread is resolved or not

## Output Format

| Filename | Comment | Author | Resolved |
|----------|---------|--------|----------|
| path/to/file.cs | The review comment text | @username | Yes |
| another/file.cs | Another comment | @username | No |

## Error Handling

- If `gh` CLI is not authenticated, prompt user to run `gh auth login`
- If no PR exists for the branch, suggest creating one with `gh pr create`
