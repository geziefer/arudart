# Kiro IDE Recommendations for ARU-DART

This document outlines recommended Kiro IDE features and configurations to improve your development workflow for the ARU-DART project.

## ✅ Already Configured

- **Python LSP (Pyright)**: Already set up in `.kiro/settings/lsp.json`
- **Steering Files**: Created for development knowledge, Python best practices, and project context
- **Specs Structure**: Created for Steps 6-10 with requirements documents

---

## 🎯 Recommended Configurations

### 1. Python Virtual Environment Configuration

**Why**: Ensure LSP uses your project's venv for accurate autocomplete and type checking

**Action**: Create `.kiro/settings/workspace.json`:

```json
{
  "python": {
    "interpreterPath": "${workspaceFolder}/venv/bin/python",
    "venvPath": "${workspaceFolder}/venv"
  }
}
```

**Benefit**: Pyright will use your installed packages (OpenCV, NumPy, etc.) for better IntelliSense

---

### 2. Testing Hook (Optional)

**Why**: Automatically run unit tests when you modify source files (not on every save, but on-demand)

**Action**: Create a hook using Kiro's hook UI or manually:

`.kiro/hooks/run-tests-on-demand.json`:
```json
{
  "name": "Run Unit Tests",
  "version": "1.0.0",
  "description": "Run pytest on modified modules",
  "when": {
    "type": "userTriggered"
  },
  "then": {
    "type": "askAgent",
    "prompt": "Run pytest for the currently modified Python files in src/. Show me a summary of test results."
  }
}
```

**Benefit**: Quick test feedback without leaving the IDE

---

### 3. Regression Test Hook

**Why**: Remind yourself to run regression tests before committing changes to detection code

**Action**: Create hook for detection file changes:

`.kiro/hooks/regression-test-reminder.json`:
```json
{
  "name": "Regression Test Reminder",
  "version": "1.0.0",
  "description": "Remind to run regression tests when detection code changes",
  "when": {
    "type": "fileEdited",
    "patterns": ["src/processing/dart_detection.py", "src/processing/coordinate_mapping.py"]
  },
  "then": {
    "type": "askAgent",
    "prompt": "Detection code was modified. Remind me to run regression tests: python tools/run_regression_tests.py"
  }
}
```

**Benefit**: Catch regressions early

---

### 4. MCP Server Recommendations

#### Option A: GitHub MCP (If using GitHub)

**Why**: Track issues, PRs, and project progress directly from Kiro

**Setup**: Add to `.kiro/settings/mcp.json`:
```json
{
  "mcpServers": {
    "github": {
      "command": "uvx",
      "args": ["mcp-server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your_token_here"
      }
    }
  }
}
```

**Benefit**: Create issues for bugs found during testing, track spec progress

#### Option B: Filesystem MCP (Built-in)

**Why**: Enhanced file operations and search

**Already Available**: Kiro has built-in filesystem tools, no setup needed

---

### 5. Code Formatting Hook (Optional)

**Why**: Automatically format Python code to PEP 8 standards

**Action**: Create hook for Python file saves:

`.kiro/hooks/format-python.json`:
```json
{
  "name": "Format Python Code",
  "version": "1.0.0",
  "description": "Run black formatter on Python files",
  "when": {
    "type": "fileEdited",
    "patterns": ["src/**/*.py", "tools/**/*.py", "tests/**/*.py"]
  },
  "then": {
    "type": "askAgent",
    "prompt": "Run black formatter on the modified Python file to ensure PEP 8 compliance"
  }
}
```

**Benefit**: Consistent code style across the project

---

### 6. Documentation Generation Hook

**Why**: Keep documentation in sync with code changes

**Action**: Create hook for major file changes:

`.kiro/hooks/update-docs.json`:
```json
{
  "name": "Update Documentation",
  "version": "1.0.0",
  "description": "Remind to update docs when major features change",
  "when": {
    "type": "fileEdited",
    "patterns": ["src/processing/*.py", "src/camera/*.py", "src/calibration/*.py"]
  },
  "then": {
    "type": "askAgent",
    "prompt": "Check if DEVELOPMENT_KNOWLEDGE.md needs updates based on the code changes"
  }
}
```

**Benefit**: Documentation stays current

---

## 🚀 Workflow Improvements

### 1. Spec-Driven Development Workflow

**Current State**: Requirements created for Steps 6-10

**Next Steps**:
1. **Review requirements** for Step 6 (Coordinate Mapping)
2. **Create design document** using Kiro's spec workflow
3. **Generate tasks** from design
4. **Execute tasks** with Kiro assistance
5. **Run tests** and validate
6. **Move to next spec** (Step 7)

**Kiro Command**: Use the spec workflow subagent to create design and tasks

---

### 2. Testing Strategy

**Unit Tests** (pytest):
- Test individual functions (coordinate transformations, score calculations)
- Mock hardware dependencies (camera frames)
- Fast execution (<1 second)

**Property-Based Tests** (hypothesis):
- Test mathematical properties (homography inverse, polar conversions)
- Generate random inputs to find edge cases
- Complement unit tests

**Integration Tests**:
- Test complete pipelines (detection → fusion → scoring)
- Use recorded images from `data/recordings/`
- Validate against ground truth

**Regression Tests**:
- Run before committing changes to detection code
- Use `tools/run_regression_tests.py`
- Ensure accuracy doesn't degrade

---

### 3. Development Cycle

**For Each Spec**:
1. **Read requirements** - Understand user stories and acceptance criteria
2. **Create design** - Technical architecture and algorithms
3. **Generate tasks** - Break down into implementable chunks
4. **Implement** - Write code following steering file guidelines
5. **Test** - Unit tests, PBT, integration tests
6. **Validate** - Run manual tests, check against acceptance criteria
7. **Document** - Update knowledge base with learnings
8. **Commit** - Save progress, move to next task

---

## 📊 Recommended Tools & Libraries

### Already Installed
- OpenCV (cv2)
- NumPy
- tomli (TOML parsing)

### Recommended Additions

**For Step 6 (Calibration)**:
```bash
pip install opencv-contrib-python  # Includes ARUCO module
```

**For Step 7.5 (Feedback System)**:
```bash
pip install matplotlib  # For heatmap generation
pip install pandas      # For data analysis
```

**For Step 9 (Web API)**:
```bash
pip install fastapi uvicorn[standard] websockets
```

**For Testing**:
```bash
pip install pytest pytest-cov hypothesis
```

---

## 🎓 Learning Resources

### Property-Based Testing
- **Hypothesis Documentation**: https://hypothesis.readthedocs.io/
- **PBT Tutorial**: Focus on testing mathematical properties (inverse functions, invariants)
- **Example**: Test that `cartesian_to_polar(polar_to_cartesian(r, θ)) == (r, θ)`

### FastAPI & WebSockets
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **WebSocket Tutorial**: https://fastapi.tiangolo.com/advanced/websockets/

### OpenCV Calibration
- **Camera Calibration Tutorial**: https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html
- **ARUCO Markers**: https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html

---

## 🔄 Continuous Improvement

### After Each Step
1. **Update LESSONS_LEARNED.md** with new insights
2. **Update DEVELOPMENT_KNOWLEDGE.md** with code patterns
3. **Run regression tests** to ensure no degradation
4. **Document configuration changes** in config.toml

### Before Moving to Next Step
1. **Review acceptance criteria** - All met?
2. **Run validation tests** - All passing?
3. **Update IMPLEMENTATION_PLAN.md** - Mark step complete
4. **Commit changes** - Save progress

---

## 🎯 Priority Actions

**Immediate** (Before starting Step 6):
1. ✅ Review Step 6 requirements
2. ⬜ Create Step 6 design document (use Kiro spec workflow)
3. ⬜ Set up Python venv configuration in Kiro
4. ⬜ Install opencv-contrib-python for ARUCO support

**Short-term** (During Steps 6-7):
1. ⬜ Create testing hooks (optional)
2. ⬜ Set up pytest with hypothesis
3. ⬜ Create calibration verification script

**Long-term** (Steps 8-10):
1. ⬜ Set up FastAPI development environment
2. ⬜ Create WebSocket test client
3. ⬜ Prepare validation session plan

---

## 📝 Notes

- **Steering files** are automatically included in Kiro's context
- **Specs** guide implementation with clear acceptance criteria
- **Hooks** are optional but can improve workflow
- **MCP servers** are optional enhancements
- **Focus on one spec at a time** for best results

---

## 🤝 Getting Help

- **Kiro Spec Workflow**: Use the requirements-first-workflow subagent
- **Code Questions**: Reference steering files for best practices
- **Testing**: Ask Kiro to help write unit tests and PBT
- **Debugging**: Use Kiro to analyze saved images and logs

---

**Ready to start Step 6!** 🎯
