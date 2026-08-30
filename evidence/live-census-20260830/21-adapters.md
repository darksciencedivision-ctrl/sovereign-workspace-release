# utc: 2026-08-30T03:42:09Z
# producer: grok-opencode LIVE-CENSUS-20260830
# host: DESKTOP-03PTABH
# adapter JSON dump


## T-RW

### debate.json
```json
{
  "id": "debate",
  "display_name": "Debate Table",
  "description": "Multi-model debate table (FastAPI, :8700)",
  "state_class": "runnable",
  "root": "D:\\producttion software 2\\release-worktree\\modules\\debate",
  "runtime_writes": [
    "${root}/config.json"
  ],
  "launch": {
    "cwd": "${root}",
    "argv": [
      "${root}/.venv/Scripts/python.exe",
      "app.py"
    ],
    "env_allowlist": [
      "SYSTEMROOT",
      "PATH",
      "TEMP",
      "TMP",
      "USERPROFILE",
      "LOCALAPPDATA",
      "APPDATA"
    ],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1"
    }
  },
  "readiness": {
    "kind": "http",
    "url": "http://127.0.0.1:8700/",
    "expect_status": 200,
    "timeout_s": 30,
    "poll_ms": 500
  },
  "identity": {
    "kind": "http_html_marker",
    "url": "http://127.0.0.1:8700/",
    "html_marker": "Debate Table"
  },
  "open": {
    "kind": "browser",
    "url": "http://127.0.0.1:8700/"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 10
  }
}
```
### distillery.json
```json
{
  "id": "distillery",
  "display_name": "Sovereign Distillery",
  "description": "Distillery runtime console — health only, no compute on open",
  "state_class": "runnable",
  "root": "D:\\producttion software 2\\release-worktree\\modules\\distillery",
  "runtime_writes": [
    "${root}/logs"
  ],
  "launch": {
    "cwd": "${root}",
    "argv": [
      "C:\\Users\\Sslaw\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
      "D:\\producttion software 2\\release-worktree\\modules\\distillery\\serve.py"
    ],
    "env_allowlist": [
      "SYSTEMROOT",
      "PATH",
      "TEMP",
      "TMP",
      "USERPROFILE"
    ],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1"
    }
  },
  "readiness": {
    "kind": "http",
    "url": "http://127.0.0.1:5184/health",
    "expect_status": 200,
    "timeout_s": 20,
    "poll_ms": 250
  },
  "identity": {
    "kind": "http_json",
    "url": "http://127.0.0.1:5184/health",
    "required_keys": [
      "ok",
      "status"
    ]
  },
  "open": {
    "kind": "browser",
    "url": "http://127.0.0.1:5184/console"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 5
  }
}
```
### llamacpp.json
```json
{
  "id": "llamacpp",
  "display_name": "llama.cpp (candidate)",
  "description": "Pinned llama.cpp router on 5183. Not production default. The paths below are a NEUTRAL PLACEHOLDER, not a real location: the llama.cpp runtime and models ship in no release archive (R2 s3), so no real path exists on any machine. llamacpp is the declared optional adapter and is skipped by the installer; supply a real runtime location before enabling it.",
  "state_class": "runnable",
  "root": "C:/sovereign-workspace/optional-runtimes/llama.cpp",
  "runtime_writes": [
    "${root}/logs"
  ],
  "launch": {
    "cwd": "${root}/current",
    "argv": [
      "C:/sovereign-workspace/optional-runtimes/llama.cpp/current/llama-server.exe",
      "--host",
      "127.0.0.1",
      "--port",
      "5183",
      "--models-dir",
      "C:/sovereign-workspace/optional-runtimes/llama.cpp/test-models",
      "--no-models-autoload"
    ],
    "env_allowlist": [
      "SYSTEMROOT",
      "PATH",
      "TEMP",
      "TMP"
    ],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1"
    }
  },
  "readiness": {
    "kind": "http",
    "url": "http://127.0.0.1:5183/models",
    "expect_status": 200,
    "timeout_s": 30,
    "poll_ms": 400
  },
  "identity": {
    "kind": "http_json",
    "url": "http://127.0.0.1:5183/models",
    "required_keys": [
      "data"
    ]
  },
  "open": {
    "kind": "none"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 8
  }
}
```
### schema.json
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "sws-adapter-v1",
  "title": "SWS Module Adapter Schema",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "id",
    "display_name",
    "description",
    "state_class",
    "root"
  ],
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9_-]{0,31}$"
    },
    "display_name": {
      "type": "string",
      "minLength": 1,
      "maxLength": 64
    },
    "description": {
      "type": "string",
      "minLength": 1,
      "maxLength": 256
    },
    "state_class": {
      "type": "string",
      "enum": [
        "runnable",
        "not_started"
      ]
    },
    "root": {
      "type": "string",
      "minLength": 1
    },
    "runtime_writes": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "default": []
    },
    "launch": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "cwd",
        "argv"
      ],
      "properties": {
        "cwd": {
          "type": "string",
          "minLength": 1
        },
        "argv": {
          "type": "array",
          "items": {
            "type": "string",
            "maxLength": 1024
          },
          "minItems": 1,
          "maxItems": 32
        },
        "env_allowlist": {
          "type": "array",
          "items": {
            "type": "string"
          },
          "default": [
            "SYSTEMROOT",
            "PATH",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA"
          ]
        },
        "env_set": {
          "type": "object",
          "additionalProperties": {
            "type": "string"
          },
          "default": {}
        }
      }
    },
    "readiness": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "kind",
        "timeout_s",
        "poll_ms"
      ],
      "properties": {
        "kind": {
          "type": "string",
          "enum": [
            "http",
            "process_window",
            "receipt_file"
          ]
        },
        "url": {
          "type": "string"
        },
        "expect_status": {
          "type": "integer",
          "minimum": 100,
          "maximum": 599
        },
        "path": {
          "type": "string"
        },
        "timeout_s": {
          "type": "integer",
          "minimum": 5,
          "maximum": 120
        },
        "poll_ms": {
          "type": "integer",
          "minimum": 250,
          "maximum": 5000
        }
      }
    },
    "identity": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "kind"
      ],
      "properties": {
        "kind": {
          "type": "string",
          "enum": [
            "http_json",
            "http_html_marker",
            "process_image"
          ]
        },
        "url": {
          "type": "string"
        },
        "required_keys": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "html_marker": {
          "type": "string"
        }
      }
    },
    "open": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "kind"
      ],
      "properties": {
        "kind": {
          "type": "string",
          "enum": [
            "browser",
            "focus_window",
            "none"
          ]
        },
        "url": {
          "type": "string"
        }
      }
    },
    "stop": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "kind",
        "grace_s"
      ],
      "properties": {
        "kind": {
          "type": "string",
          "enum": [
            "job_object"
          ]
        },
        "grace_s": {
          "type": "integer",
          "minimum": 1,
          "maximum": 30
        }
      }
    },
    "startup_test": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "env_set": {
          "type": "object",
          "additionalProperties": {
            "type": "string"
          },
          "default": {}
        },
        "readiness": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "kind",
            "path"
          ],
          "properties": {
            "kind": {
              "type": "string",
              "enum": [
                "receipt_file"
              ]
            },
            "path": {
              "type": "string",
              "minLength": 1
            },
            "require": {
              "type": "object"
            },
            "timeout_s": {
              "type": "integer",
              "minimum": 5,
              "maximum": 120
            },
            "poll_ms": {
              "type": "integer",
              "minimum": 250,
              "maximum": 5000
            }
          }
        }
      }
    }
  },
  "allOf": [
    {
      "if": {
        "properties": {
          "state_class": {
            "const": "runnable"
          }
        }
      },
      "then": {
        "required": [
          "launch",
          "readiness",
          "identity",
          "open",
          "stop"
        ]
      }
    }
  ]
}
```
### sovereign.json
```json
{
  "id": "sovereign",
  "display_name": "SOVEREIGN",
  "description": "Operator product service and UI (Flask, :5175)",
  "state_class": "runnable",
  "root": "D:\\producttion software 2\\release-worktree\\modules\\sovereign",
  "runtime_writes": [
    "${root}/runtime",
    "${root}/published",
    "${root}/library/queues",
    "${root}/logs"
  ],
  "launch": {
    "cwd": "${root}",
    "argv": [
      "${root}/.venv/Scripts/python.exe",
      "-m",
      "sovereign_product.server",
      "--root",
      "${root}",
      "--host",
      "127.0.0.1",
      "--port",
      "5175",
      "--workers",
      "1"
    ],
    "env_allowlist": [
      "SYSTEMROOT",
      "PATH",
      "TEMP",
      "TMP",
      "USERPROFILE",
      "LOCALAPPDATA",
      "APPDATA"
    ],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1"
    }
  },
  "readiness": {
    "kind": "http",
    "url": "http://127.0.0.1:5175/v1/health",
    "expect_status": 200,
    "timeout_s": 45,
    "poll_ms": 500
  },
  "identity": {
    "kind": "http_json",
    "url": "http://127.0.0.1:5175/v1/health",
    "required_keys": [
      "status",
      "product_version"
    ]
  },
  "open": {
    "kind": "browser",
    "url": "http://127.0.0.1:5175/"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 10
  }
}
```
### sow.json
```json
{
  "id": "sow",
  "display_name": "Multi-Model Terminal",
  "description": "Sovereign Orchestration Workspace (Electron + xterm.js)",
  "state_class": "runnable",
  "root": "D:\\producttion software 2\\release-worktree\\modules\\sow",
  "runtime_writes": [
    "${root}/apps/desktop/.recovery",
    "${root}/docs/evidence/receipts"
  ],
  "launch": {
    "cwd": "${root}/apps/desktop",
    "argv": [
      "${root}/apps/desktop/node_modules/electron/dist/electron.exe",
      "."
    ],
    "env_allowlist": [
      "SYSTEMROOT",
      "PATH",
      "TEMP",
      "TMP",
      "USERPROFILE",
      "LOCALAPPDATA",
      "APPDATA"
    ],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1",
      "SOW_CONDUCTOR_AUTOLAUNCH": "0",
      "SOW_OPERATOR_TEXT_DRIVER_PORT": "17890"
    }
  },
  "readiness": {
    "kind": "receipt_file",
    "path": "${root}/docs/evidence/receipts/SHELL-LIVE-READY.json",
    "timeout_s": 90,
    "poll_ms": 1000
  },
  "identity": {
    "kind": "process_image"
  },
  "open": {
    "kind": "focus_window"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 15
  },
  "startup_test": {
    "env_set": {
      "SHELL_SELFCHECK": "1"
    },
    "readiness": {
      "kind": "receipt_file",
      "path": "${root}/docs/evidence/receipts/PHASE16A_SELFCHECK.json",
      "require": {
        "ok": true
      },
      "timeout_s": 90,
      "poll_ms": 1000
    }
  }
}
```
### tokencenter.json
```json
{
  "id": "tokencenter",
  "display_name": "Token Center",
  "description": "Read-only local usage telemetry. No credentials.",
  "state_class": "runnable",
  "root": "D:\\producttion software 2\\release-worktree\\modules\\tokencenter",
  "runtime_writes": [
    "${root}/data"
  ],
  "launch": {
    "cwd": "${root}",
    "argv": [
      "C:\\Users\\Sslaw\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
      "D:\\producttion software 2\\release-worktree\\modules\\tokencenter\\piggybank.py",
      "--port",
      "8765"
    ],
    "env_allowlist": [
      "SYSTEMROOT",
      "PATH",
      "TEMP",
      "TMP",
      "USERPROFILE",
      "LOCALAPPDATA",
      "APPDATA"
    ],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1"
    }
  },
  "readiness": {
    "kind": "http",
    "url": "http://127.0.0.1:8765/healthz",
    "expect_status": 200,
    "timeout_s": 20,
    "poll_ms": 250
  },
  "identity": {
    "kind": "http_json",
    "url": "http://127.0.0.1:8765/healthz",
    "required_keys": [
      "ok",
      "collector_error"
    ]
  },
  "open": {
    "kind": "browser",
    "url": "http://127.0.0.1:8765/"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 5
  }
}
```

## T-PW

### debate.json
```json
{
  "id": "debate",
  "display_name": "Debate Table",
  "description": "Multi-model debate table (FastAPI, :8700)",
  "state_class": "runnable",
  "root": "D:/Product Software/Production Workspace/modules/debate",
  "runtime_writes": ["${root}/config.json"],
  "launch": {
    "cwd": "${root}",
    "argv": ["${root}/.venv/Scripts/python.exe", "app.py"],
    "env_allowlist": ["SYSTEMROOT", "PATH", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA"],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1"
    }
  },
  "readiness": {
    "kind": "http",
    "url": "http://127.0.0.1:8700/",
    "expect_status": 200,
    "timeout_s": 30,
    "poll_ms": 500
  },
  "identity": {
    "kind": "http_html_marker",
    "url": "http://127.0.0.1:8700/",
    "html_marker": "Debate Table"
  },
  "open": {
    "kind": "browser",
    "url": "http://127.0.0.1:8700/"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 10
  }
}
```
### distillery.json
```json
{
  "id": "distillery",
  "display_name": "Sovereign Distillery",
  "description": "Distillery runtime console \u2014 health only, no compute on open",
  "state_class": "runnable",
  "root": "D:/Product Software/Production Workspace/modules/distillery",
  "runtime_writes": [
    "${root}/logs"
  ],
  "launch": {
    "cwd": "${root}",
    "argv": [
      "C:/Users/Sslaw/AppData/Local/Programs/Python/Python312/python.exe",
      "D:/Product Software/Production Workspace/modules/distillery/serve.py"
    ],
    "env_allowlist": [
      "SYSTEMROOT",
      "PATH",
      "TEMP",
      "TMP",
      "USERPROFILE"
    ],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1"
    }
  },
  "readiness": {
    "kind": "http",
    "url": "http://127.0.0.1:5184/health",
    "expect_status": 200,
    "timeout_s": 20,
    "poll_ms": 250
  },
  "identity": {
    "kind": "http_json",
    "url": "http://127.0.0.1:5184/health",
    "required_keys": [
      "ok",
      "status"
    ]
  },
  "open": {
    "kind": "browser",
    "url": "http://127.0.0.1:5184/console"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 5
  }
}
```
### llamacpp.json
```json
{
  "id": "llamacpp",
  "display_name": "llama.cpp (candidate)",
  "description": "Pinned llama.cpp router on 5183. Not production default.",
  "state_class": "runnable",
  "root": "D:/Product Software/Production Workspace/runtime/llama.cpp",
  "runtime_writes": [
    "${root}/logs"
  ],
  "launch": {
    "cwd": "${root}/current",
    "argv": [
      "D:/Product Software/Production Workspace/runtime/llama.cpp/current/llama-server.exe",
      "--host",
      "127.0.0.1",
      "--port",
      "5183",
      "--models-dir",
      "D:/Product Software/Production Workspace/runtime/llama.cpp/test-models",
      "--no-models-autoload"
    ],
    "env_allowlist": [
      "SYSTEMROOT",
      "PATH",
      "TEMP",
      "TMP"
    ],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1"
    }
  },
  "readiness": {
    "kind": "http",
    "url": "http://127.0.0.1:5183/models",
    "expect_status": 200,
    "timeout_s": 30,
    "poll_ms": 400
  },
  "identity": {
    "kind": "http_json",
    "url": "http://127.0.0.1:5183/models",
    "required_keys": [
      "data"
    ]
  },
  "open": {
    "kind": "none"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 8
  }
}
```
### schema.json
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "sws-adapter-v1",
  "title": "SWS Module Adapter Schema",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "id",
    "display_name",
    "description",
    "state_class",
    "root"
  ],
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9_-]{0,31}$"
    },
    "display_name": {
      "type": "string",
      "minLength": 1,
      "maxLength": 64
    },
    "description": {
      "type": "string",
      "minLength": 1,
      "maxLength": 256
    },
    "state_class": {
      "type": "string",
      "enum": [
        "runnable",
        "not_started"
      ]
    },
    "root": {
      "type": "string",
      "minLength": 1
    },
    "runtime_writes": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "default": []
    },
    "launch": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "cwd",
        "argv"
      ],
      "properties": {
        "cwd": {
          "type": "string",
          "minLength": 1
        },
        "argv": {
          "type": "array",
          "items": {
            "type": "string",
            "maxLength": 1024
          },
          "minItems": 1,
          "maxItems": 32
        },
        "env_allowlist": {
          "type": "array",
          "items": {
            "type": "string"
          },
          "default": [
            "SYSTEMROOT",
            "PATH",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA"
          ]
        },
        "env_set": {
          "type": "object",
          "additionalProperties": {
            "type": "string"
          },
          "default": {}
        }
      }
    },
    "readiness": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "kind",
        "timeout_s",
        "poll_ms"
      ],
      "properties": {
        "kind": {
          "type": "string",
          "enum": [
            "http",
            "process_window",
            "receipt_file"
          ]
        },
        "url": {
          "type": "string"
        },
        "expect_status": {
          "type": "integer",
          "minimum": 100,
          "maximum": 599
        },
        "path": {
          "type": "string"
        },
        "timeout_s": {
          "type": "integer",
          "minimum": 5,
          "maximum": 120
        },
        "poll_ms": {
          "type": "integer",
          "minimum": 250,
          "maximum": 5000
        }
      }
    },
    "identity": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "kind"
      ],
      "properties": {
        "kind": {
          "type": "string",
          "enum": [
            "http_json",
            "http_html_marker",
            "process_image"
          ]
        },
        "url": {
          "type": "string"
        },
        "required_keys": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "html_marker": {
          "type": "string"
        }
      }
    },
    "open": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "kind"
      ],
      "properties": {
        "kind": {
          "type": "string",
          "enum": [
            "browser",
            "none"
          ]
        },
        "url": {
          "type": "string"
        }
      }
    },
    "stop": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "kind",
        "grace_s"
      ],
      "properties": {
        "kind": {
          "type": "string",
          "enum": [
            "job_object"
          ]
        },
        "grace_s": {
          "type": "integer",
          "minimum": 1,
          "maximum": 30
        }
      }
    },
    "startup_test": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "env_set": {
          "type": "object",
          "additionalProperties": {
            "type": "string"
          },
          "default": {}
        },
        "readiness": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "kind",
            "path"
          ],
          "properties": {
            "kind": {
              "type": "string",
              "enum": [
                "receipt_file"
              ]
            },
            "path": {
              "type": "string",
              "minLength": 1
            },
            "require": {
              "type": "object"
            },
            "timeout_s": {
              "type": "integer",
              "minimum": 5,
              "maximum": 120
            },
            "poll_ms": {
              "type": "integer",
              "minimum": 250,
              "maximum": 5000
            }
          }
        }
      }
    }
  },
  "allOf": [
    {
      "if": {
        "properties": {
          "state_class": {
            "const": "runnable"
          }
        }
      },
      "then": {
        "required": [
          "launch",
          "readiness",
          "identity",
          "open",
          "stop"
        ]
      }
    }
  ]
}
```
### sovereign.json
```json
{
  "id": "sovereign",
  "display_name": "SOVEREIGN",
  "description": "Operator product service and UI (Flask, :5175)",
  "state_class": "runnable",
  "root": "D:/Product Software/Production Workspace/modules/sovereign",
  "runtime_writes": ["${root}/runtime", "${root}/published", "${root}/library/queues", "${root}/logs"],
  "launch": {
    "cwd": "${root}",
    "argv": ["${root}/.venv/Scripts/python.exe", "-m", "sovereign_product.server", "--root", "${root}", "--host", "127.0.0.1", "--port", "5175", "--workers", "1"],
    "env_allowlist": ["SYSTEMROOT", "PATH", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA"],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1"
    }
  },
  "readiness": {
    "kind": "http",
    "url": "http://127.0.0.1:5175/v1/health",
    "expect_status": 200,
    "timeout_s": 45,
    "poll_ms": 500
  },
  "identity": {
    "kind": "http_json",
    "url": "http://127.0.0.1:5175/v1/health",
    "required_keys": ["status", "product_version"]
  },
  "open": {
    "kind": "browser",
    "url": "http://127.0.0.1:5175/"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 10
  }
}
```
### sow.json
```json
{
  "id": "sow",
  "display_name": "Multi-Model Terminal",
  "description": "Sovereign Orchestration Workspace (Electron + xterm.js)",
  "state_class": "runnable",
  "root": "D:/Product Software/Production Workspace/modules/sow",
  "runtime_writes": [
    "${root}/apps/desktop/.recovery",
    "${root}/docs/evidence/receipts"
  ],
  "launch": {
    "cwd": "${root}/apps/desktop",
    "argv": [
      "${root}/apps/desktop/node_modules/electron/dist/electron.exe",
      "."
    ],
    "env_allowlist": [
      "SYSTEMROOT",
      "PATH",
      "TEMP",
      "TMP",
      "USERPROFILE",
      "LOCALAPPDATA",
      "APPDATA"
    ],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1",
      "SOW_CONDUCTOR_AUTOLAUNCH": "0",
      "SOW_OPERATOR_TEXT_DRIVER_PORT": "17890"
    }
  },
  "readiness": {
    "kind": "receipt_file",
    "path": "${root}/docs/evidence/receipts/SHELL-LIVE-READY.json",
    "timeout_s": 90,
    "poll_ms": 1000
  },
  "identity": {
    "kind": "process_image"
  },
  "open": {
    "kind": "none"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 15
  },
  "startup_test": {
    "env_set": {
      "SHELL_SELFCHECK": "1"
    },
    "readiness": {
      "kind": "receipt_file",
      "path": "${root}/docs/evidence/receipts/PHASE16A_SELFCHECK.json",
      "require": {
        "ok": true
      },
      "timeout_s": 90,
      "poll_ms": 1000
    }
  }
}
```
### tokencenter.json
```json
{
  "id": "tokencenter",
  "display_name": "Token Center",
  "description": "Read-only local usage telemetry. No credentials.",
  "state_class": "runnable",
  "root": "D:/Product Software/Production Workspace/modules/tokencenter",
  "runtime_writes": [
    "${root}/data"
  ],
  "launch": {
    "cwd": "${root}",
    "argv": [
      "C:/Users/Sslaw/AppData/Local/Programs/Python/Python312/python.exe",
      "D:/Product Software/Production Workspace/modules/tokencenter/piggybank.py",
      "--port",
      "8765"
    ],
    "env_allowlist": [
      "SYSTEMROOT",
      "PATH",
      "TEMP",
      "TMP",
      "USERPROFILE",
      "LOCALAPPDATA",
      "APPDATA"
    ],
    "env_set": {
      "PYTHONDONTWRITEBYTECODE": "1"
    }
  },
  "readiness": {
    "kind": "http",
    "url": "http://127.0.0.1:8765/healthz",
    "expect_status": 200,
    "timeout_s": 20,
    "poll_ms": 250
  },
  "identity": {
    "kind": "http_json",
    "url": "http://127.0.0.1:8765/healthz",
    "required_keys": [
      "ok",
      "collector_error"
    ]
  },
  "open": {
    "kind": "browser",
    "url": "http://127.0.0.1:8765/"
  },
  "stop": {
    "kind": "job_object",
    "grace_s": 5
  }
}
```
