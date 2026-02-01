# Getting Started with Spec-Driven Development

## Overview

This guide helps you start implementing Step 6 (Coordinate Mapping) using Kiro's spec-driven development workflow.

---

## Step-by-Step Guide

### 1. Review Requirements

**File**: `.kiro/specs/step-6-coordinate-mapping/requirements.md`

**What to look for**:
- User stories (US-6.1 through US-6.5)
- Acceptance criteria (AC-6.x.x)
- Technical constraints
- Dependencies
- Success metrics

**Action**: Read through the requirements and make sure you understand:
- What needs to be built
- Why it's needed
- How success is measured

---

### 2. Create Design Document

**Goal**: Define the technical architecture and implementation approach

**Ask Kiro**:
```
Create the design document for Step 6 (Coordinate Mapping) based on the requirements in 
.kiro/specs/step-6-coordinate-mapping/requirements.md

Include:
1. Technical architecture (classes, modules, data flow)
2. Algorithms for intrinsic calibration (chessboard method)
3. Algorithms for extrinsic calibration (ARUCO markers + homography)
4. CoordinateMapper class interface
5. Property-based test properties for coordinate transformations
6. Error handling strategy
7. Configuration parameters

Follow the steering file guidelines for Python best practices.
```

**Kiro will create**: `.kiro/specs/step-6-coordinate-mapping/design.md`

---

### 3. Review Design

**What to check**:
- ✅ Architecture makes sense
- ✅ Algorithms are correct (OpenCV calibration methods)
- ✅ Interfaces are well-defined
- ✅ PBT properties are testable
- ✅ Error handling is comprehensive
- ✅ Configuration is flexible

**Provide feedback**: If anything needs clarification or changes

---

### 4. Generate Tasks

**Ask Kiro**:
```
Generate the tasks list for Step 6 (Coordinate Mapping) based on the design document.

Break down into:
1. Setup tasks (directory structure, dependencies)
2. Intrinsic calibration tasks
3. ARUCO marker generation tasks
4. Extrinsic calibration tasks
5. CoordinateMapper implementation tasks
6. Testing tasks (unit tests + PBT)
7. Verification tasks

Prioritize tasks in implementation order.
```

**Kiro will create**: `.kiro/specs/step-6-coordinate-mapping/tasks.md`

---

### 5. Execute Tasks

**For each task**:

1. **Mark task as in progress**:
   ```
   Update task status to "in_progress" for task X.Y in 
   .kiro/specs/step-6-coordinate-mapping/tasks.md
   ```

2. **Implement the task**:
   ```
   Implement task X.Y: [task description]
   
   Follow the design document and steering file guidelines.
   Write clean, well-documented code with type hints.
   ```

3. **Write tests**:
   ```
   Write unit tests for [module/function].
   
   For coordinate transformations, also write property-based tests using hypothesis.
   ```

4. **Validate**:
   ```
   Run tests and verify the implementation meets acceptance criteria AC-X.Y.Z
   ```

5. **Mark task as complete**:
   ```
   Update task status to "completed" for task X.Y
   ```

---

### 6. Checkpoint Review

**After completing all tasks**:

1. **Run all tests**:
   ```bash
   pytest tests/test_calibration.py -v
   pytest tests/test_coordinate_mapping.py -v
   ```

2. **Run verification script**:
   ```bash
   python calibration/verify_calibration.py
   ```

3. **Check acceptance criteria**:
   - Review each AC-6.x.x
   - Verify all are met

4. **Update documentation**:
   ```
   Update DEVELOPMENT_KNOWLEDGE.md with:
   - Calibration process learnings
   - Configuration values used
   - Common issues and solutions
   ```

5. **Update IMPLEMENTATION_PLAN.md**:
   - Mark Step 6 as complete
   - Add results and notes

---

## Property-Based Testing Examples

### Example 1: Homography Inverse Property

```python
from hypothesis import given, strategies as st
import numpy as np

@given(
    x=st.floats(min_value=-170, max_value=170),
    y=st.floats(min_value=-170, max_value=170)
)
def test_coordinate_mapping_inverse(x, y):
    """Test that mapping to image and back gives original coordinates."""
    mapper = CoordinateMapper(camera_id=0)
    
    # Board → Image → Board
    u, v = mapper.board_to_image(x, y)
    x_back, y_back = mapper.image_to_board(u, v)
    
    # Should be close to original (within 1mm tolerance)
    assert abs(x_back - x) < 1.0
    assert abs(y_back - y) < 1.0
```

### Example 2: Polar Conversion Property

```python
@given(
    r=st.floats(min_value=0, max_value=170),
    theta=st.floats(min_value=0, max_value=2*np.pi)
)
def test_polar_cartesian_inverse(r, theta):
    """Test that polar → cartesian → polar gives original coordinates."""
    # Polar → Cartesian
    x, y = polar_to_cartesian(r, theta)
    
    # Cartesian → Polar
    r_back, theta_back = cartesian_to_polar(x, y)
    
    # Should match (within floating point tolerance)
    assert abs(r_back - r) < 0.001
    # Angle might wrap around, so check modulo 2π
    assert abs((theta_back - theta) % (2*np.pi)) < 0.001
```

---

## Common Kiro Commands

### Spec Workflow

```
# Create design from requirements
"Create the design document for Step 6 based on requirements"

# Generate tasks from design
"Generate tasks for Step 6 based on the design document"

# Update task status
"Mark task 6.1 as in_progress"
"Mark task 6.1 as completed"
```

### Implementation

```
# Implement a task
"Implement task 6.2: Create intrinsic calibration script"

# Write tests
"Write unit tests for the CoordinateMapper class"
"Write property-based tests for coordinate transformations"

# Debug
"Help me debug this calibration error: [error message]"
"Review this code for potential issues: [code]"
```

### Documentation

```
# Update knowledge base
"Update DEVELOPMENT_KNOWLEDGE.md with calibration learnings"

# Generate docstrings
"Add docstrings to this function following the steering file format"
```

---

## Tips for Success

1. **Read steering files first**: They contain critical lessons learned
2. **One task at a time**: Don't skip ahead
3. **Test as you go**: Write tests alongside implementation
4. **Use PBT for math**: Coordinate transformations are perfect for PBT
5. **Save images**: Calibration images are useful for debugging
6. **Document learnings**: Update DEVELOPMENT_KNOWLEDGE.md as you go
7. **Ask Kiro for help**: Code review, test generation, debugging

---

## Troubleshooting

### Issue: Calibration reprojection error too high

**Solution**: 
- Capture more chessboard images (30+ recommended)
- Ensure images cover different angles and distances
- Check chessboard pattern is flat and well-lit

### Issue: ARUCO markers not detected

**Solution**:
- Verify marker IDs match config
- Check lighting (avoid glare on markers)
- Ensure markers are flat and not occluded
- Try different ARUCO dictionary if needed

### Issue: Homography gives unrealistic coordinates

**Solution**:
- Verify marker positions are measured correctly
- Check marker corners are detected accurately
- Ensure board coordinate system is defined correctly
- Try more markers (6 instead of 4)

---

## Next Steps After Step 6

Once Step 6 is complete and validated:

1. **Review Step 7 requirements** (Multi-Camera Fusion)
2. **Create Step 7 design**
3. **Implement Step 7**
4. **Continue through Steps 8, 9, 10**

---

**Ready to start? Open the Step 6 requirements and begin!** 🚀
