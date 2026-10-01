# Response playbooks

The active playbook is `response_playbooks.json`. The validation API accepts JSON, YAML, DOCX and PDF files up to 5 MB. Validation does not activate or overwrite a playbook.

JSON and YAML files must use the same fields as the active playbook. DOCX and PDF files may contain normal human-readable guidance, but must also include a JSON or YAML section between these markers:

```text
PLAYBOOK_DATA_START
version: "1.1"
levels:
  monitor: &sample_actions
    - category: monitoring
      action: Review daily signals
      owner: Surveillance analyst
      timeframe: Daily
      requires_approval: false
  investigate: *sample_actions
  escalate: *sample_actions
condition_guidance:
  ili: [Review respiratory testing demand]
  age: [Review food and water exposure reports]
  dengue: [Review rainfall and vector activity]
PLAYBOOK_DATA_END
```

Every severity level must contain at least one action. Each action requires `category`, `action`, `owner`, `timeframe`, and a Boolean `requires_approval` value.
