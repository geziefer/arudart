# ARU-DART Transition to Kiro Spec-Driven Development

## ✅ Completed

### 1. Steering Files Created
- **`.kiro/steering/development-knowledge.md`** - Critical lessons learned, code patterns, configuration values
- **`.kiro/steering/python-best-practices.md`** - Python coding standards, OpenCV patterns, testing guidelines
- **`.kiro/steering/project-context.md`** - Project overview, hardware setup, current status

**Purpose**: These files are automatically included in Kiro's context, ensuring consistent development practices.

---

### 2. Specs Created (Steps 6-10)

All specs have **requirements.md** complete with user stories and acceptance criteria:

| Spec | Directory | Status | Key Features |
|------|-----------|--------|--------------|
| **Step 6** | `step-6-coordinate-mapping/` | ✅ Requirements | Intrinsic/extrinsic calibration, ARUCO markers, homography |
| **Step 7** | `step-7-multi-camera-fusion/` | ✅ Requirements | Coordinate fusion, score derivation, event creation |
| **Step 7.5** | `step-7.5-feedback-system/` | ✅ Requirements | User feedback, accuracy analysis, verified dataset |
| **Step 8** | `step-8-state-machine/` | ✅ Requirements | Throw sequence, multi-dart tracking, event model |
| **Step 9** | `step-9-web-api/` | ✅ Requirements | REST endpoints, WebSocket streaming, JSON events |
| **Step 10** | `step-10-poc-validation/` | ✅ Requirements | Validation session, accuracy analysis, final report |

**Next Steps**: Create design documents and tasks for each spec.

---

### 3. Python LSP Configured
- **Pyright** already configured in `.kiro/settings/lsp.json`
- Provides autocomplete, type checking, and error detection
- Works with your venv (recommend adding venv path to workspace settings)

---

## 📋 Next Actions

### Immediate (Start Step 6)

1. **Review Step 6 Requirements**
   ```bash
   # Open in Kiro
   .kiro/specs/step-6-coordinate-mapping/requirements.md
   ```

2. **Create Design Document**
   - Use Kiro's spec workflow to generate design
   - Include technical architecture, algorithms, data structures
   - Define interfaces for CoordinateMapper class

3. **Generate Tasks**
   - Break design into implementable tasks
   - Prioritize: intrinsic calibration → ARUCO setup → extrinsic calibration → verification

4. **Execute Tasks**
   - Implement one task at a time
   - Write tests (unit + PBT for transformations)
   - Validate against acceptance criteria

---

### Property-Based Testing Strategy

**Use PBT For** (Hybrid Approach):
- ✅ **Coordinate transformations** (Step 6)
  - Property: `image_to_board(board_to_image(x, y)) ≈ (x, y)`
  - Property: Homography preserves collinearity
  
- ✅ **Fusion algorithms** (Step 7)
  - Property: Weighted average within bounds of inputs
  - Property: Outlier rejection removes extreme values
  
- ✅ **Score mapping** (Step 7)
  - Property: `cartesian_to_polar(polar_to_cartesian(r, θ)) == (r, θ)`
  - Property: Sector determination is consistent across angle wraparound

**Use Traditional Tests For**:
- ❌ Hardware-dependent code (camera capture, image processing)
- ❌ State machine (scenario-based integration tests)
- ❌ API (HTTP/WebSocket integration tests)

**Libraries**:
```bash
pip install hypothesis  # Property-based testing
pip install pytest pytest-cov  # Unit testing
```

---

### Recommended Kiro Features

**Optional but Helpful**:

1. **Testing Hook** (User-triggered)
   - Manually run tests on modified files
   - See `KIRO_RECOMMENDATIONS.md` for setup

2. **Regression Test Reminder**
   - Reminds you to run regression tests when detection code changes
   - Prevents accuracy degradation

3. **Python Venv Configuration**
   - Add venv path to `.kiro/settings/workspace.json`
   - Improves LSP accuracy

**See `KIRO_RECOMMENDATIONS.md` for detailed setup instructions.**

---

## 🎯 Development Workflow

### For Each Spec (6, 7, 7.5, 8, 9, 10):

1. **Requirements** ✅ (Already done)
   - User stories with acceptance criteria
   - Technical constraints
   - Dependencies

2. **Design** ⬜ (Next step)
   - Technical architecture
   - Algorithms and data structures
   - Interface definitions
   - PBT properties to test

3. **Tasks** ⬜ (After design)
   - Break design into implementable chunks
   - Prioritize tasks
   - Estimate effort

4. **Implementation** ⬜ (Execute tasks)
   - Write code following steering file guidelines
   - Write tests (unit + PBT where applicable)
   - Validate against acceptance criteria

5. **Validation** ⬜ (After implementation)
   - Run all tests
   - Manual testing with hardware
   - Update documentation

6. **Checkpoint** ⬜ (Before next spec)
   - Review with user
   - Update IMPLEMENTATION_PLAN.md
   - Commit changes

---

## 📚 Documentation Structure

```
arudart/
├── .kiro/
│   ├── steering/              # Always-included context
│   │   ├── development-knowledge.md
│   │   ├── python-best-practices.md
│   │   └── project-context.md
│   ├── specs/                 # Spec-driven development
│   │   ├── README.md          # Specs overview
│   │   ├── step-6-coordinate-mapping/
│   │   │   ├── requirements.md  ✅
│   │   │   ├── design.md        ⬜
│   │   │   └── tasks.md         ⬜
│   │   ├── step-7-multi-camera-fusion/
│   │   ├── step-7.5-feedback-system/
│   │   ├── step-8-state-machine/
│   │   ├── step-9-web-api/
│   │   └── step-10-poc-validation/
│   └── settings/
│       └── lsp.json           # Python LSP configured
├── IMPLEMENTATION_PLAN.md     # Original plan (reference)
├── TESTING_PLAN.md            # Test cases (reference)
├── DEVELOPMENT_KNOWLEDGE.md   # Knowledge base (reference)
├── LESSONS_LEARNED.md         # Lessons (reference)
├── KIRO_RECOMMENDATIONS.md    # Kiro feature recommendations
└── TRANSITION_SUMMARY.md      # This file
```

---

## 🚀 Ready to Start!

**You're all set to begin Step 6 (Coordinate Mapping)!**

### Quick Start:

1. **Open Step 6 requirements** in Kiro
2. **Ask Kiro to create the design document**:
   ```
   "Create the design document for Step 6 (Coordinate Mapping) based on the requirements. 
   Include technical architecture, algorithms for intrinsic/extrinsic calibration, 
   and property-based test properties for coordinate transformations."
   ```
3. **Review the design** and provide feedback
4. **Generate tasks** from the design
5. **Start implementing** task by task

---

## 💡 Tips

- **Use steering files**: They're automatically included in Kiro's context
- **One spec at a time**: Complete Step 6 before moving to Step 7
- **Test as you go**: Write tests alongside implementation
- **Update docs**: Keep DEVELOPMENT_KNOWLEDGE.md current with learnings
- **Run regression tests**: Before committing changes to detection code
- **Ask Kiro for help**: Code review, test generation, debugging

---

## 📞 Questions?

- **Spec workflow**: Ask Kiro to explain the requirements-first workflow
- **PBT**: Ask Kiro for examples of property-based tests for coordinate transformations
- **Design patterns**: Reference steering files for established patterns
- **Testing**: Ask Kiro to help write unit tests and PBT

---

**Happy coding! 🎯🎲**
