<!-- Derived from Anthropic skill-creator (Apache-2.0); modified for OMP. -->
# JSON contracts and judgment schemas

## Contents
- [Data contracts](#data-contracts): §3.1 evals; §3.2 metadata; §3.3 run; §3.4 timing; §3.5 grading; §3.6 benchmark; §3.7 feedback; §3.8 trigger set; §3.9 trigger results; §3.10 description improvement; §3.11 loop results
- [Field notes](#field-notes)
- [Comparison and analysis artifact contracts](#comparison-and-analysis-artifact-contracts)
- [Strict task output schemas](#strict-task-output-schemas)
  - [Grader output](#grader-output)
  - [Comparator output](#comparator-output)
  - [Analyzer post-hoc output](#analyzer-post-hoc-output)
  - [Analyzer benchmark output](#analyzer-benchmark-output)

## Data contracts

### 3.1 `<skill>/evals/evals.json` (authored; lives in the skill dir)

**Producer:** The skill author. **Consumer:** run_evals.py and the grader.
```json
{
  "skill_name": "csv-cleaner",
  "evals": [
    {"id": 1, "name": "messy-contacts", "prompt": "realistic user request…",
     "expected_output": "human description of success",
     "files": ["evals/files/contacts.csv"],
     "assertions": ["Output CSV has header name,email,company"]}
  ]
}
```
`id` unique int; `files` relative to skill dir (optional); `assertions` optional list of strings (upstream `expectations` key: accept as alias on read, never write it).

### 3.2 `eval_metadata.json`

**Producer:** run_evals.py (or the author updating assertions). **Consumer:** grader, review viewer, and prepare_blind.py.
`{"eval_id":1,"eval_name":"messy-contacts","prompt":"…","expected_output":"…","files":["…"],"assertions":["…"]}`. run_evals writes it from evals.json **but preserves an existing file's non-empty `assertions`** if evals.json has none for that eval.

### 3.3 `run.json` (run_evals)

**Producer:** run_evals.py. **Consumer:** grader, aggregate_benchmark.py, review viewer, and post-hoc analyzer.
```json
{"run_id":"eval-1-messy-contacts/with_skill/run-1","eval_id":1,"eval_name":"messy-contacts",
 "configuration":"with_skill","replicate":1,"iteration":1,
 "skill_name":"csv-cleaner","skill_path":"<abs frozen copy or null>",
 "prompt_mode":"skill-invocation|skill-discovery|plain",
 "env":"isolated|ambient","model_requested":"@default","thinking":"medium|null",
 "model_resolved":"provider/model or null","outcome":"completed|timeout|error|aborted",
 "exit_code":0,"error":null,"started_at":"ISO-8601Z","ended_at":"ISO-8601Z","wall_ms":12345,
 "contamination":{"read_skill":false,"evidence":[]},
 "omp_argv":["omp","…"]}
```
`contamination.read_skill`: for `without_skill` arm, true if any tool call referenced `skill://<name>` or a path inside the frozen candidate/baseline copy or the original skill dir; for skill arms always computed too (informational).

### 3.4 `timing.json` (run_evals; measured, never estimated)

**Producer:** run_evals.py. **Consumer:** aggregate_benchmark.py, review viewer, and post-hoc analyzer.
```json
{"total_tokens":84852,"input_tokens":80000,"output_tokens":3000,"cache_read_tokens":1852,"cache_write_tokens":0,
 "cost_usd":0.0123,"requests":7,"duration_ms":23332,"total_duration_seconds":23.3,
 "model_time_ms":15000,"tool_calls":{"bash":3,"write":2},"tool_errors":1,
 "token_scope":"assistant message_end usage; excludes background description compression"}
```
Sum `usage.*` over `message_end` events with `message.role=="assistant"` only (never turn_end/agent_end). `total_tokens` = Σ`usage.totalTokens` (already includes cache reads). `duration_ms` = wall clock of the subprocess. `model_time_ms` = Σ`message.duration`. Missing data → `null`, never 0-filled guesses.

### 3.5 `grading.json` (grader role writes; viewer + aggregator read)

**Producer:** grader role. **Consumer:** aggregate_benchmark.py and review viewer.
```json
{"expectations":[{"text":"…","passed":true,"evidence":"…"}],
 "summary":{"passed":2,"failed":1,"total":3,"pass_rate":0.67},
 "claims":[{"claim":"…","type":"factual|process|quality","verified":true,"evidence":"…"}],
 "eval_feedback":{"suggestions":[{"assertion":"…","reason":"…"}],"overall":"…"},
 "user_notes_summary":{"uncertainties":[],"needs_review":[],"workarounds":[]}}
```
Required: `expectations[].text/passed/evidence`, `summary`. Others optional. (Upstream `execution_metrics`/`timing` inside grading are dropped — metrics come from timing.json.)

### 3.6 `benchmark.json` (aggregate_benchmark; viewer Benchmark tab)

**Producer:** aggregate_benchmark.py; the parent merges analyzer notes. **Consumer:** review viewer and analyzer benchmark mode.
```json
{"metadata":{"skill_name":"…","skill_path":"…","iteration":1,"timestamp":"ISO","evals_run":[1,2],
   "runs_per_configuration":1,"primary":"with_skill","baseline":"without_skill","models":["provider/model"]},
 "runs":[{"run_id":"…","eval_id":1,"eval_name":"…","configuration":"with_skill","run_number":1,
   "result":{"pass_rate":0.67,"passed":2,"failed":1,"total":3,"time_seconds":23.3,"tokens":84852,
             "cost_usd":0.0123,"tool_calls":5,"errors":0,"outcome":"completed"},
   "expectations":[{"text":"…","passed":true,"evidence":"…"}],"notes":[]}],
 "run_summary":{
   "with_skill":{"pass_rate":{"mean":0.8,"stddev":0.1,"min":0.6,"max":1.0,"n":3},
                 "time_seconds":{…},"tokens":{…},"cost_usd":{…}},
   "without_skill":{…},
   "delta":{"pass_rate":"+0.50","time_seconds":"+13.0","tokens":"+1700","cost_usd":"+0.0040"}},
 "notes":["analyst observation…"]}
```
Stats skip `null`s (`n` = count of non-null); stddev = sample (n−1), 0 when n<2; numbers rounded to 4 dp. `delta` = primary − baseline (sign always shown; `null` if either side missing). Ungraded runs: `pass_rate:null`. Re-running the aggregator **preserves existing top-level `notes`**.

### 3.7 `feedback.json` (viewer writes)

**Producer:** review viewer. **Consumer:** the parent improvement workflow and later review viewer.
```json
{"status":"in_progress|complete","updated_at":"ISO",
 "reviews":[{"run_id":"eval-1-x/with_skill/run-1","feedback":"axis labels missing","visited":true,"timestamp":"ISO"}]}
```
`visited:false` + empty feedback = not reviewed (NOT approval).

### 3.8 Trigger eval set `<skill>/evals/trigger-evals.json`

**Producer:** the skill author. **Consumer:** run_trigger_eval.py and run_loop.py.
`[{"id":1,"query":"…","should_trigger":true}]` — `id` optional on input (scripts assign stable 1-based ids if missing); reject duplicate queries with conflicting labels.

### 3.9 `run_trigger_eval.py` output

**Producer:** run_trigger_eval.py. **Consumer:** improve_description.py, run_loop.py, and the parent.
```json
{"skill_name":"…","description":"authored description evaluated","regime":"warm|cold",
 "model_requested":"…","models_resolved":["…"],
 "warm_ready":true,"warm_hint":"compressed routing hint or null",
 "rendered_hints":{"<hint text>":12,"<other>":3},
 "results":[{"id":1,"query":"…","should_trigger":true,"trigger_rate":0.67,"triggers":2,"valid_runs":3,
   "invalid_runs":{"timeout":0,"error":0,"hint_mismatch":0},"hints":["…"],"pass":true}],
 "summary":{"total":20,"passed":17,"failed":2,"invalid":1},
 "usage":{"total_tokens":12345,"cost_usd":0.01,"note":"excludes background description compression"}}
```
`pass` = `(trigger_rate >= threshold) == should_trigger`, computed over valid runs; if `valid_runs == 0` → `pass:null` and counted in `summary.invalid`.
`warm_ready` is boolean and `warm_hint` is a string or null. In warm mode, `warm_ready:false` means trials were scored under mixed or unknown hints, not a verified uniform warm hint. `invalid_runs.hint_mismatch` counts trials whose rendered hint differed from the locked hint; those trials are excluded from `valid_runs` and `trigger_rate`, never counted as non-triggers.

### 3.10 `improve_description.py` output

**Producer:** improve_description.py. **Consumer:** run_loop.py and subsequent improve_description.py calls.
`{"description":"new","history":[...prior, {"description":"evaluated one","passed":n,"failed":n,"total":n,"results":[...],"rendered_hints":{...}}]}`

### 3.11 `run_loop.py` output (`results.json`)

**Producer:** run_loop.py. **Consumer:** generate_report.py and the parent.
`{"skill_name","original_description","best_description":"selected description or null","best_score":"7/8 test","best_iteration":2,"regime","model","holdout":0.4,"seed":42,"iterations":[{"iteration":1,"description":"…","train":{summary,results,"warm_ready":true,"warm_hint":"hint or null"},"test":{summary,results,"warm_ready":true,"warm_hint":"hint or null"}|null,"rendered_hints":{…},"warm_ready":true,"hint_mismatches":{"train":0,"test":0}}],"stopped_because":"all_train_passed|max_iterations|infrastructure_failure"}`. Never edits SKILL.md.
Each iteration records `warm_ready` and `hint_mismatches.train/test` counts; each non-null train/test split records `warm_ready` and `warm_hint` with the same meaning and types as §3.9. Per-query results retain `invalid_runs.hint_mismatch`. `infrastructure_failure` means reliable scoring could not continue; `best_description` can be null if no eligible candidate exists, so never apply it blindly.

## Field notes

The §3 contracts above preserve the design field names, with §3.9 and §3.11 extended to document the implemented warm-hint integrity and infrastructure-failure outputs. Ellipses and vertical-bar alternatives are contract notation, not literal JSON values. Examples in §3.10 and §3.11 are shorthand descriptions, not directly parseable fixtures. Use the actual producer output as JSON.

- Evals: skill_name matches frontmatter; evals[].name supplies the directory slug; prompt is the actual user request and expected_output describes success. assertions are checks, not the prompt.
- Metadata: eval_id/eval_name identify the case; prompt/expected_output/files/assertions preserve its authored context.
- Run: configuration is with_skill, without_skill, or old_skill; replicate is one-based. Paths identify frozen skill copies; null means no skill. Requested and resolved models differ in purpose. Outcome and error describe infrastructure completion, not assertion success. Contamination evidence records skill references, not inferred benefit. omp_argv is the actual invocation.
- Timing: cache counts and total_tokens must not be double-counted; cost is USD. requests counts assistant messages with usage; tool_calls is a per-tool count map, tool_errors counts failed tool calls. token_scope defines what was measured.
- Grading: expectations preserves assertion text and cites evidence; passed/failed/total must agree with its entries; pass_rate is passed/total (0 for no assertions, with missing coverage noted). Optional claims verify factual/process/quality statements; eval_feedback critiques discriminating coverage; user_notes_summary groups executor concerns. Metrics do not belong here.
- Benchmark: metadata identifies arms, samples, iteration, and resolved models; runs retains identities, expectations, and notes. result holds grading and measured resources; ungraded outcomes remain null. run_summary is per-configuration statistics and signed primary-minus-baseline delta; top-level notes are analyst observations.
- Feedback: status is workflow progress, not approval; updated_at and per-review timestamp record saves. run_id maps to benchmark/runs identities. visited distinguishes unreviewed empty feedback from reviewed empty feedback.
- Trigger sets: query is a realistic routing request; should_trigger is the authored label, not an observed result.
- Trigger results: rendered_hints counts actual routing hint texts; triggers and valid_runs determine trigger_rate. invalid_runs separates infrastructure failures. summary invalid counts unscorable queries; usage excludes background compression.
- Description improvement: description is the proposed text; history records each evaluated candidate, scores, per-query results, and hints.
- Loop: original_description is unchanged source text; best_description is selected output, not an applied edit. best_score labels its scoring split; iterations distinguish train/test; null test means no holdout. stopped_because records the stopping rule. Holdout scores used for selection are not an unbiased final test.

## Comparison and analysis artifact contracts

**comparison.json** — Producer: comparator role; consumer: post-hoc analyzer and parent. Stored at the caller-specified path, normally in the blind eval directory. winner is A, B, or TIE. reasoning cites task evidence; rubric.A/B holds adapted numeric content and structure criteria, dimension means and overall score (dimension means summed). output_quality.A/B.score equals rubric overall_score; strengths and weaknesses cite specifics. expectation_results is omitted without assertions; otherwise details preserve text and boolean verdicts, with passed/total/pass_rate consistent.

**analysis.json** — Producer: post-hoc analyzer; consumer: parent improvement workflow. comparison_summary records comparator result and unblinded paths. winner_strengths, loser_weaknesses, instruction_following, improvement_suggestions, and transcript_insights follow the upstream structure shown in the role example and schema. For TIE, winner_skill/loser_skill are null, winner_strengths/loser_weaknesses are empty; instruction_following.winner/loser and transcript_insights.winner_execution_pattern/loser_execution_pattern correspond to A/B respectively, labelled explicitly in text. Suggestions identify which side they target, without claiming a loser.

For a no-skill side (`run.json.skill_path:null`), its comparison_summary skill path is null, including a decisive comparison. Skip reading that side's SKILL.md. Its required instruction_following.score is null and issues contains the explicit string "not applicable: no skill"; issue entries permit string or null, without removing the required issues array. Analyze that side's task behavior from its outputs and transcript, not imagined skill instructions. Suggestions cannot target a nonexistent skill.

**Benchmark notes object** — Producer: analyzer benchmark mode; consumer: parent, which merges notes into benchmark.json.notes without rewriting aggregates. The object is {"notes":[string]}, not a bare array; notes are observations only.

## Strict task output schemas

Use these JSON objects as each task item’s outputSchema and set schemaMode to "strict". Only the documented subset of JSON Schema keywords is used. Closed objects reject extra fields; comparator content/structure deliberately accept task-specific numeric criterion names via additionalProperties. Optional fields remain optional; consumers must not assume their presence. Semantic arithmetic, score ranges, evidence quality, and conditional TIE rules are enforced by role instructions, not unsupported schema keywords.

### Grader output

```json
{
  "type": "object",
  "properties": {
    "expectations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "text": {
            "type": "string"
          },
          "passed": {
            "type": "boolean"
          },
          "evidence": {
            "type": "string"
          }
        },
        "required": [
          "text",
          "passed",
          "evidence"
        ],
        "additionalProperties": false
      }
    },
    "summary": {
      "type": "object",
      "properties": {
        "passed": {
          "type": "integer"
        },
        "failed": {
          "type": "integer"
        },
        "total": {
          "type": "integer"
        },
        "pass_rate": {
          "type": "number"
        }
      },
      "required": [
        "passed",
        "failed",
        "total",
        "pass_rate"
      ],
      "additionalProperties": false
    },
    "claims": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "claim": {
            "type": "string"
          },
          "type": {
            "type": "string",
            "enum": [
              "factual",
              "process",
              "quality"
            ]
          },
          "verified": {
            "type": "boolean"
          },
          "evidence": {
            "type": "string"
          }
        },
        "required": [
          "claim",
          "type",
          "verified",
          "evidence"
        ],
        "additionalProperties": false
      }
    },
    "eval_feedback": {
      "type": "object",
      "properties": {
        "suggestions": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "assertion": {
                "type": "string"
              },
              "reason": {
                "type": "string"
              }
            },
            "required": [
              "reason"
            ],
            "additionalProperties": false
          }
        },
        "overall": {
          "type": "string"
        }
      },
      "required": [
        "suggestions",
        "overall"
      ],
      "additionalProperties": false
    },
    "user_notes_summary": {
      "type": "object",
      "properties": {
        "uncertainties": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "needs_review": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "workarounds": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      },
      "required": [
        "uncertainties",
        "needs_review",
        "workarounds"
      ],
      "additionalProperties": false
    }
  },
  "required": [
    "expectations",
    "summary"
  ],
  "additionalProperties": false
}
```

### Comparator output

```json
{
  "type": "object",
  "properties": {
    "winner": {
      "type": "string",
      "enum": [
        "A",
        "B",
        "TIE"
      ]
    },
    "reasoning": {
      "type": "string"
    },
    "rubric": {
      "type": "object",
      "properties": {
        "A": {
          "type": "object",
          "properties": {
            "content": {
              "type": "object",
              "properties": {},
              "additionalProperties": {
                "type": "number"
              }
            },
            "structure": {
              "type": "object",
              "properties": {},
              "additionalProperties": {
                "type": "number"
              }
            },
            "content_score": {
              "type": "number"
            },
            "structure_score": {
              "type": "number"
            },
            "overall_score": {
              "type": "number"
            }
          },
          "required": [
            "content",
            "structure",
            "content_score",
            "structure_score",
            "overall_score"
          ],
          "additionalProperties": false
        },
        "B": {
          "type": "object",
          "properties": {
            "content": {
              "type": "object",
              "properties": {},
              "additionalProperties": {
                "type": "number"
              }
            },
            "structure": {
              "type": "object",
              "properties": {},
              "additionalProperties": {
                "type": "number"
              }
            },
            "content_score": {
              "type": "number"
            },
            "structure_score": {
              "type": "number"
            },
            "overall_score": {
              "type": "number"
            }
          },
          "required": [
            "content",
            "structure",
            "content_score",
            "structure_score",
            "overall_score"
          ],
          "additionalProperties": false
        }
      },
      "required": [
        "A",
        "B"
      ],
      "additionalProperties": false
    },
    "output_quality": {
      "type": "object",
      "properties": {
        "A": {
          "type": "object",
          "properties": {
            "score": {
              "type": "number"
            },
            "strengths": {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            "weaknesses": {
              "type": "array",
              "items": {
                "type": "string"
              }
            }
          },
          "required": [
            "score",
            "strengths",
            "weaknesses"
          ],
          "additionalProperties": false
        },
        "B": {
          "type": "object",
          "properties": {
            "score": {
              "type": "number"
            },
            "strengths": {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            "weaknesses": {
              "type": "array",
              "items": {
                "type": "string"
              }
            }
          },
          "required": [
            "score",
            "strengths",
            "weaknesses"
          ],
          "additionalProperties": false
        }
      },
      "required": [
        "A",
        "B"
      ],
      "additionalProperties": false
    },
    "expectation_results": {
      "type": "object",
      "properties": {
        "A": {
          "type": "object",
          "properties": {
            "passed": {
              "type": "integer"
            },
            "total": {
              "type": "integer"
            },
            "pass_rate": {
              "type": "number"
            },
            "details": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "text": {
                    "type": "string"
                  },
                  "passed": {
                    "type": "boolean"
                  }
                },
                "required": [
                  "text",
                  "passed"
                ],
                "additionalProperties": false
              }
            }
          },
          "required": [
            "passed",
            "total",
            "pass_rate",
            "details"
          ],
          "additionalProperties": false
        },
        "B": {
          "type": "object",
          "properties": {
            "passed": {
              "type": "integer"
            },
            "total": {
              "type": "integer"
            },
            "pass_rate": {
              "type": "number"
            },
            "details": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "text": {
                    "type": "string"
                  },
                  "passed": {
                    "type": "boolean"
                  }
                },
                "required": [
                  "text",
                  "passed"
                ],
                "additionalProperties": false
              }
            }
          },
          "required": [
            "passed",
            "total",
            "pass_rate",
            "details"
          ],
          "additionalProperties": false
        }
      },
      "required": [
        "A",
        "B"
      ],
      "additionalProperties": false
    }
  },
  "required": [
    "winner",
    "reasoning",
    "rubric",
    "output_quality"
  ],
  "additionalProperties": false
}
```

### Analyzer post-hoc output

```json
{
  "type": "object",
  "properties": {
    "comparison_summary": {
      "type": "object",
      "properties": {
        "winner": {
          "type": "string",
          "enum": [
            "A",
            "B",
            "TIE"
          ]
        },
        "winner_skill": {
          "type": [
            "string",
            "null"
          ]
        },
        "loser_skill": {
          "type": [
            "string",
            "null"
          ]
        },
        "comparator_reasoning": {
          "type": "string"
        }
      },
      "required": [
        "winner",
        "winner_skill",
        "loser_skill",
        "comparator_reasoning"
      ],
      "additionalProperties": false
    },
    "winner_strengths": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "loser_weaknesses": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "instruction_following": {
      "type": "object",
      "properties": {
        "winner": {
          "type": "object",
          "properties": {
            "score": {
              "type": ["number", "null"]
            },
            "issues": {
              "type": "array",
              "items": {
                "type": ["string", "null"]
              }
            }
          },
          "required": [
            "score",
            "issues"
          ],
          "additionalProperties": false
        },
        "loser": {
          "type": "object",
          "properties": {
            "score": {
              "type": ["number", "null"]
            },
            "issues": {
              "type": "array",
              "items": {
                "type": ["string", "null"]
              }
            }
          },
          "required": [
            "score",
            "issues"
          ],
          "additionalProperties": false
        }
      },
      "required": [
        "winner",
        "loser"
      ],
      "additionalProperties": false
    },
    "improvement_suggestions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "priority": {
            "type": "string",
            "enum": [
              "high",
              "medium",
              "low"
            ]
          },
          "category": {
            "type": "string",
            "enum": [
              "instructions",
              "tools",
              "examples",
              "error_handling",
              "structure",
              "references"
            ]
          },
          "suggestion": {
            "type": "string"
          },
          "expected_impact": {
            "type": "string"
          }
        },
        "required": [
          "priority",
          "category",
          "suggestion",
          "expected_impact"
        ],
        "additionalProperties": false
      }
    },
    "transcript_insights": {
      "type": "object",
      "properties": {
        "winner_execution_pattern": {
          "type": "string"
        },
        "loser_execution_pattern": {
          "type": "string"
        }
      },
      "required": [
        "winner_execution_pattern",
        "loser_execution_pattern"
      ],
      "additionalProperties": false
    }
  },
  "required": [
    "comparison_summary",
    "winner_strengths",
    "loser_weaknesses",
    "instruction_following",
    "improvement_suggestions",
    "transcript_insights"
  ],
  "additionalProperties": false
}
```

### Analyzer benchmark output

```json
{
  "type": "object",
  "properties": {
    "notes": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  },
  "required": [
    "notes"
  ],
  "additionalProperties": false
}
```
