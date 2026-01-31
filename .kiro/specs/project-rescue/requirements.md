# Project Rescue - Requirements

## Current State Analysis (现状分析)

### Problems Identified (问题识别)

**P1: Test Infrastructure Collapse**
- **Symptom**: Deleted 8000+ tests, coverage dropped from 80%+ to unknown
- **Root Cause**: Tests were poorly organized, many duplicates, low actual coverage despite high count
- **Impact**: No safety net for refactoring, regression risks skyrocketed

**P2: Planning File Chaos**
- **Symptom**: `task_plan.md`, `progress.md`, `findings.md` in root AND `.kiro/specs/`
- **Root Cause**: Copilot not respecting `.kiro` structure, creates files in project root
- **Impact**: Cannot track work, duplicate information, confusion

**P3: Documentation Language Inconsistency**
- **Symptom**: Comments/docs in Japanese, Chinese, English within same files
- **Root Cause**: No enforcement of language rules, LLMs inherit existing style
- **Impact**: Hard to maintain, confusing for contributors

**P4: Code Quality Variance**
- **Symptom**: Same file has inconsistent comment styles despite quality scripts
- **Root Cause**: Quality scripts exist but not integrated into workflow
- **Impact**: Technical debt accumulates, readability suffers

**P5: Python Support Not Industry-Leading**
- **Symptom**: Python plugin exists but not optimized to maximum potential
- **Root Cause**: Not following Level 2-3 optimization process systematically
- **Impact**: Cannot use as template for other languages

---

## Goals & Objectives (目标定义)

### Primary Goals

**G1: Restore Test Infrastructure with TDD**
- Rebuild test suite using TDD methodology
- Target: 80%+ coverage with meaningful tests
- Focus: Quality over quantity

**G2: Establish Planning Discipline**
- Enforce `.kiro` structure for ALL planning files
- Automate checks to prevent root-level planning files
- Integrate with Copilot workflow

**G3: Unified English Documentation**
- Convert all comments/docs to English
- Establish pre-commit hooks to enforce
- Create migration script for existing code

**G4: Code Quality Automation**
- Integrate quality scripts into pre-commit hooks
- Make 90/100 score mandatory for commits
- Create auto-fix tools where possible

**G5: Achieve Industry-Leading Python Support**
- Apply Level 2-3 optimization to `python_plugin.py` and `python_formatter.py`
- Document optimization patterns
- Use as template for other languages

---

## Non-Functional Requirements (非功能性要求)

### Performance
- Quality checks must run < 5 seconds per file
- Test suite must run < 2 minutes for quick feedback

### Maintainability
- All code must have English comments
- All code must score >= 90/100 on quality check
- All code must have corresponding tests

### Developer Experience
- Pre-commit hooks catch issues before commit
- Clear error messages guide developers to fixes
- Automated tools fix common issues

### Consistency
- Single source of truth for planning: `.kiro/specs/`
- Single language for docs: English
- Single quality standard: 90/100 minimum

---

## Use Cases (用例场景)

### UC1: Starting New Feature
**Actor**: Developer using Copilot
**Flow**:
1. Copilot creates `.kiro/specs/{feature}/` directory
2. Creates `requirements.md`, `design.md`, `tasks.md`
3. Pre-commit hook validates structure
4. If files in wrong location, hook blocks commit

**Success Criteria**: No planning files outside `.kiro/specs/`

### UC2: Writing Python Code
**Actor**: Developer
**Flow**:
1. Write code following Level 2-3 standards
2. Run `python scripts/check_code_quality.py <file>`
3. If score < 90, fix issues
4. Pre-commit hook validates on commit
5. Hook blocks if score < 90

**Success Criteria**: All committed Python code scores >= 90/100

### UC3: Writing Tests with TDD
**Actor**: Developer
**Flow**:
1. Write failing test first
2. Implement minimal code to pass
3. Refactor while keeping tests green
4. Coverage tracked automatically

**Success Criteria**: No code committed without tests

### UC4: Converting Existing Code to English
**Actor**: Migration script
**Flow**:
1. Scan file for non-English comments
2. Extract comment text
3. Translate to English (manual review)
4. Replace in-place
5. Verify quality score maintained

**Success Criteria**: All comments in English, quality score >= 90

---

## Glossary (术语表)

**Level 2-3 Optimization**: Process defined in `.kiro/steering/tech.md` requiring:
- 11-section module header
- 3 custom exception classes
- Args/Returns/Note for all public methods
- 5-8 performance monitoring points
- Statistics tracking
- `__all__` exports
- Score >= 90/100

**TDD (Test-Driven Development)**: Write tests first, then implement code to pass tests

**Pre-commit Hook**: Git hook that runs before commit, blocks commit if checks fail

**Quality Score**: Numeric score (0-100) from `check_code_quality.py` measuring:
- Documentation completeness
- Exception handling
- Performance monitoring
- Code organization

**Planning Structure**: `.kiro/specs/{feature-name}/` with:
- `requirements.md`: What and why
- `design.md`: How
- `tasks.md`: Step-by-step breakdown
- `progress.md`: Session log (optional)

---

## Constraints (约束)

### Must Have
- All code in English
- All code >= 90/100 quality score
- All features have tests
- All planning in `.kiro/specs/`

### Must Not
- No planning files in project root
- No mixed-language comments
- No code < 90/100 quality score
- No features without tests

### Dependencies
- Existing quality check scripts
- Pre-commit framework installed
- TDD workflow skill available
- File-based planning skill available

---

## Success Metrics (验收标准)

### M1: Test Coverage
- **Target**: >= 80% line coverage
- **Measurement**: `pytest --cov=tree_sitter_analyzer`
- **Timeline**: Phase 1 (Python plugin first)

### M2: Code Quality
- **Target**: 100% of files >= 90/100 score
- **Measurement**: `python scripts/check_code_quality.py --check-all`
- **Timeline**: Phase 2 (Python first, then others)

### M3: Documentation Language
- **Target**: 100% English comments
- **Measurement**: `grep -r "[\u4e00-\u9fa5]" tree_sitter_analyzer/`
- **Timeline**: Phase 3 (automated script)

### M4: Planning Discipline
- **Target**: Zero planning files outside `.kiro/specs/`
- **Measurement**: `ls *.md | grep -E "(task_plan|progress|findings)"`
- **Timeline**: Phase 0 (immediate cleanup)

### M5: Python Excellence
- **Target**: `python_plugin.py` and `python_formatter.py` both 97-100/100
- **Measurement**: Quality check + external review
- **Timeline**: Phase 1 (foundation for others)

---

## Risk Analysis (风险分析)

**R1: Time Investment**
- **Risk**: Rescue takes months, same as original investment
- **Mitigation**: Phase-based approach, deliver value incrementally
- **Priority**: High

**R2: Breaking Changes**
- **Risk**: Refactoring breaks existing functionality
- **Mitigation**: TDD ensures tests catch regressions
- **Priority**: High

**R3: LLM Non-Compliance**
- **Risk**: Copilot continues ignoring rules despite hooks
- **Mitigation**: Education + tooling + strict enforcement
- **Priority**: Medium

**R4: Motivation Loss**
- **Risk**: Project owner burns out from rework
- **Mitigation**: Quick wins in Phase 0, visible progress
- **Priority**: High

---

## Phase Overview (阶段概览)

**Phase 0: Emergency Cleanup (1 day)**
- Move scattered planning files to `.kiro/specs/rescue-cleanup/`
- Install pre-commit hooks
- Document current state

**Phase 1: Python Excellence (1 week)**
- Apply Level 2-3 to `python_plugin.py`
- Apply Level 2-3 to `python_formatter.py`
- Write comprehensive tests (TDD)
- Document optimization patterns

**Phase 2: Test Infrastructure (2 weeks)**
- Rebuild core tests using TDD
- Focus on critical paths first
- Achieve 80%+ coverage on core modules

**Phase 3: Language Standardization (1 week)**
- Create translation script
- Convert all comments to English
- Update contributing guidelines

**Phase 4: Quality Automation (3 days)**
- Integrate quality checks into pre-commit
- Create auto-fix scripts
- Document workflow

**Phase 5: Propagate to Other Languages (2 weeks)**
- Apply Python patterns to Java, JavaScript, etc.
- Systematic optimization
- Knowledge transfer

---

## Decision Log (决策记录)

**D1: Why Python First?**
- **Rationale**: You stated goal is to optimize Python first, learn patterns, then apply to others
- **Alternative Considered**: Fix all languages simultaneously
- **Decision**: Python first, systematic approach

**D2: Why TDD?**
- **Rationale**: Tests deleted, need rebuild. TDD ensures quality from start
- **Alternative Considered**: Write code first, tests later
- **Decision**: TDD enforced, use `tdd-workflow` skill

**D3: Why English Only?**
- **Rationale**: Project targets international audience, English is industry standard
- **Alternative Considered**: Keep mixed languages
- **Decision**: Unified English, migration script for conversion

**D4: Why 90/100 Score Minimum?**
- **Rationale**: Based on Level 2-3 optimization process in `tech.md`
- **Alternative Considered**: Lower threshold (80/100)
- **Decision**: 90/100 aligns with existing standards

---

## References (参考资料)

- `.kiro/steering/tech.md`: Level 2-3 optimization process
- `scripts/check_code_quality.py`: Quality scoring tool
- `CODING_STANDARDS.md`: Project coding standards
- `.kiro/optimization_work/README.md`: Optimization workflow
- `CLAUDE.md`: Claude-specific development guidelines
