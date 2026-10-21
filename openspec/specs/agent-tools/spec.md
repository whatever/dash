# agent-tools Specification

## Purpose

What the agent can do during a turn: run commands in the sandbox, fetch and search the web, search and add memories, and use the tools of configured MCP servers. A per-tool policy decides which tools are offered and which wait for a person's approval.

## Requirements

### Requirement: The agent can run commands in the sandbox

The agent SHALL have a `run_command` tool. It runs a shell command over SSH in the `dash-sandbox` pod, in the directory `/config/workspace`, and returns the exit code and the combined output. It connects as `SANDBOX_USER` (default `agent`) to `SANDBOX_HOST` and `SANDBOX_PORT` (default 2222). The worker SHALL hold only the SSH key; the Nango and GitHub tokens SHALL stay in the sandbox.

#### Scenario: A command succeeds

- **WHEN** the agent runs `git --version`
- **THEN** the tool returns exit code 0 and the git version printed in the sandbox

#### Scenario: A command fails

- **WHEN** the agent runs a command that exits with status 2
- **THEN** the tool returns exit code 2 and the command's output, and the turn continues

### Requirement: Sandbox commands are bounded

A sandbox command that runs longer than 90 seconds SHALL be stopped, and the tool SHALL report the timeout. Output past 20,000 characters SHALL be cut and marked as cut.

#### Scenario: A command hangs

- **WHEN** a command is still running after 90 seconds
- **THEN** it is stopped and the tool reports a timeout

#### Scenario: Long output

- **WHEN** a command prints 50,000 characters
- **THEN** the tool returns the first 20,000 characters and says the output was cut

### Requirement: The agent can fetch a web page

The agent SHALL have a `fetch_url` tool for `http` and `https` URLs.
- It SHALL refuse any URL whose host resolves to a private, loopback, link-local or reserved address. That check SHALL also apply to every redirect, with at most 5 redirects.
- It SHALL read at most 1 MB of the body.
- It SHALL return the page as text, cut to 20,000 characters.

#### Scenario: A public page

- **WHEN** the agent fetches a public HTML page
- **THEN** the tool returns the page's text without markup

#### Scenario: An internal address

- **WHEN** the agent fetches a URL whose host resolves to `127.0.0.1` or a `10.0.0.0/8` address
- **THEN** the tool refuses it without making the request

#### Scenario: A redirect to an internal address

- **WHEN** a public URL redirects to an internal address
- **THEN** the tool refuses the redirect and returns an error

### Requirement: The agent can search the web

Unless `AGENT_WEB_SEARCH` is `off`, the agent SHALL be able to search the web. It SHALL use the model's own web search where the model has one, and otherwise a DuckDuckGo search that the worker runs. When `AGENT_WEB_SEARCH` is `off`, the agent SHALL be offered no search tool.

#### Scenario: A model without its own search

- **WHEN** the configured model has no native web search and `AGENT_WEB_SEARCH` is unset
- **THEN** the agent is offered a DuckDuckGo search tool

#### Scenario: Search turned off

- **WHEN** `AGENT_WEB_SEARCH` is `off`
- **THEN** no search tool is offered, and every other tool still works

### Requirement: The agent can search and add memories

The agent SHALL have a `search_memories` tool and a `remember` tool.
- `search_memories` returns up to 8 memories nearest a query, with their distance.
- `remember` stores a fact with source `agent`, unless a stored memory is within cosine distance 0.08 of it.

#### Scenario: Remembering a fact

- **WHEN** the agent remembers `The user prefers Celsius.` and no similar memory exists
- **THEN** a memory with that text and source `agent` is stored

#### Scenario: A repeat

- **WHEN** the agent remembers a fact within 0.08 of a stored memory
- **THEN** nothing new is stored, and the tool says it was already known

### Requirement: Configured MCP servers add tools

The worker SHALL read `AGENT_MCP_SERVERS`, a JSON list of servers, each with a `name`, a streamable-HTTP `url`, and an optional `exclude` list of tool names. It SHALL offer each server's tools to the agent, named `<name>_<tool>`, except the excluded ones. A server that cannot be reached when a turn starts SHALL be left out of that turn, with a `status` event naming it.

#### Scenario: An excluded tool

- **WHEN** a server named `serena` is configured with `exclude` `["execute_shell_command"]`
- **THEN** the agent is offered `serena_*` tools but not `serena_execute_shell_command`

#### Scenario: A server is down

- **WHEN** a configured server does not answer at the start of a turn
- **THEN** the turn proceeds without its tools, and the job has a `status` event naming the server

### Requirement: Each tool follows a policy

The worker SHALL read `AGENT_TOOL_POLICY`, a JSON map from a tool name to `never`, `ask` or `auto`. A key `<server>_*` applies to every tool from that MCP server. A tool without an entry SHALL be `auto`.
- A `never` tool SHALL NOT be offered to the model.
- An `auto` tool SHALL run when the model calls it.

#### Scenario: A tool set to never

- **WHEN** `AGENT_TOOL_POLICY` is `{"run_command": "never"}`
- **THEN** the model is not offered `run_command`, and every other tool is offered as usual

#### Scenario: A whole server

- **WHEN** `AGENT_TOOL_POLICY` is `{"serena_*": "never"}`
- **THEN** no tool from the `serena` server is offered
