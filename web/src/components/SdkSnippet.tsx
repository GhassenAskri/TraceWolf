import { CodeSnippet } from '@carbon/react'

/** The code that sends calls to a project, with its slug filled in (shown when a project is created). */
export default function SdkSnippet({ slug }: { slug: string }) {
  // JSON.stringify gives a valid double-quoted Python string.
  const code = `import aicontrol
from openai import OpenAI

aicontrol.init(project=${JSON.stringify(slug)})   # once at startup (or set AICONTROL_PROJECT)

client = OpenAI()
client.responses.create(model="gpt-5-mini", input="What is the capital of France?")`

  return (
    <CodeSnippet type="multi" feedback="Copied">
      {code}
    </CodeSnippet>
  )
}
