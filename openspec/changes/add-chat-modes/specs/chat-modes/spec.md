## ADDED Requirements

### Requirement: A conversation has a mode

The system SHALL give each conversation a `mode` of `manual`, `fast_forward`, `auto`, `plan` or `dangerously_skip`. A conversation SHALL start in `fast_forward`. A client SHALL be able to read the mode and change it to any of these values, and the system SHALL reject any other value.

#### Scenario: A new conversation

- **WHEN** a conversation is created
- **THEN** its mode is `fast_forward`

#### Scenario: An unknown mode

- **WHEN** a client sets a mode that is not one of the five
- **THEN** the request is rejected and the mode is unchanged

### Requirement: A mode change applies from the next turn

A change of mode SHALL apply to turns that start after it. A turn already running, and approvals already open, SHALL keep the mode they began under.

#### Scenario: Changing the mode mid-turn

- **WHEN** the mode changes while a turn is running
- **THEN** that turn finishes under the old mode and the next turn uses the new one

### Requirement: Manual mode asks for every call

In `manual` mode every tool call SHALL wait for a person's approval, including calls to tools the deployment policy marks `auto`.

#### Scenario: An auto tool

- **WHEN** the agent calls a tool the policy marks `auto` in a `manual` conversation
- **THEN** the call waits for approval

### Requirement: Fast-forward mode follows the saved rules

In `fast_forward` mode a call to a tool the policy marks `ask` SHALL run without asking when a saved allow rule covers the tool, and SHALL otherwise wait for approval. A call to a tool marked `auto` SHALL run.

#### Scenario: A covered tool

- **WHEN** the agent calls an `ask` tool that has a saved allow rule
- **THEN** it runs without an approval

#### Scenario: An uncovered tool

- **WHEN** the agent calls an `ask` tool with no saved rule
- **THEN** it waits for approval

### Requirement: Auto mode lets a classifier decide

In `auto` mode the system SHALL decide for each call whether it needs a person. A call on a fixed list of always-ask calls SHALL wait for approval whatever the classifier says. For any other call the classifier SHALL decide, and when the classifier fails, times out or is unsure, the call SHALL wait for approval.

#### Scenario: A listed call

- **WHEN** the agent makes a call on the always-ask list
- **THEN** it waits for approval even if the classifier would allow it

#### Scenario: The classifier is down

- **WHEN** the classifier errors or times out
- **THEN** the call waits for approval

### Requirement: Plan mode withholds side effects until a plan is approved

In `plan` mode the agent SHALL be offered only tools without side effects until a person approves a plan. Approving the plan SHALL end the restriction for later turns.

#### Scenario: Before approval

- **WHEN** the agent runs in `plan` mode and no plan is approved
- **THEN** tools with side effects are not offered to the model

#### Scenario: After approval

- **WHEN** a person approves the plan
- **THEN** later turns are offered the tools again under the conversation's mode

### Requirement: Dangerously-skip mode asks for nothing

In `dangerously_skip` mode no tool call SHALL wait for approval. Tools the policy marks `never` SHALL stay hidden. The mode SHALL be set per conversation and SHALL NOT be the default for any conversation.

#### Scenario: An ask tool

- **WHEN** the agent calls an `ask` tool in a `dangerously_skip` conversation
- **THEN** it runs without an approval

#### Scenario: A never tool

- **WHEN** a tool is marked `never`
- **THEN** it is not offered to the model in any mode
