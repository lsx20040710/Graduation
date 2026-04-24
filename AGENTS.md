# AGENTS.md

## Project identity

This repository is for an undergraduate thesis project focused on:
"Visual servo control for a rope-driven soft robot used in sea cucumber harvesting experiments".

The current implementation target is:
- a two-joint rope-driven soft robot
- six servos directly controlled by a PC through USB/TTL
- one USB camera for visual feedback
- a closed loop from image error to servo command and robot response

This project should NOT be treated as:
- a generic object detection demo
- a ROS2-first software stack at the current stage
- an STM32 lower-controller project at the current stage
- a standard 6-DOF rigid industrial manipulator project

The robot structure should currently be understood as:
- each joint is composed of three units
- each joint is driven by three tendons
- the full robot has two joints and six tendons in total
- the current mechanism references `DewiEtAl-2024-TendonDrivenContinuumRobot-ModularStiffness-ZHTranslation.pdf.pdf`
  conceptually, but is modified and scaled for this project

## Primary goals

When analyzing, modifying, or generating code, always prioritize:

1. Building or improving a closed-loop pipeline:
   visual detection -> image-space target error -> six-servo command -> rope-driven soft robot response -> execution feedback

2. Preserving project structure and existing module boundaries whenever possible

3. Making the system runnable, debuggable, and easy to integrate on the current PC + USB/TTL hardware path

4. Ensuring the code fits the kinematic and control characteristics of a two-joint, three-tendon-per-joint soft robot,
   rather than assuming a rigid serial manipulator

## Research and reference policy

When solving technical problems, prioritize the following evidence sources in order:

1. Uploaded papers, local PDFs, notes, and project documents already present in the repository
2. High-quality academic sources such as Google Scholar indexed papers, IEEE, Springer, Elsevier, and authoritative surveys
3. Strong open-source reference implementations on GitHub from active and technically credible repositories

If internet access is unavailable, explicitly say so and then:
- rely on local papers and repository materials first
- infer conservatively
- avoid pretending that an online literature review was performed

When referencing papers or external projects:
- prefer recent and relevant work
- summarize what is borrowed conceptually
- do not mechanically copy implementation details
- adapt ideas to this project's actual hardware and software constraints

## Coding style requirements

All generated code must follow these rules:

1. Keep formatting clean and conventional
2. Use clear naming, consistent structure, and minimal unnecessary abstraction
3. Every important function, class, node, callback, and control block should have useful comments
4. Comments must explain purpose, inputs/outputs, assumptions, and key logic
5. Avoid AI-sounding filler comments and avoid overexplaining trivial lines
6. Prefer practical, maintainable code over flashy or overengineered code
7. Do not silently change architecture without strong reason
8. When editing existing code, preserve original style where reasonable while improving clarity

## Current system understanding

At the current stage, the mainline architecture is:

Top layer:
- PC-side visual processing
- target extraction and image-error computation
- servo command generation

Execution layer:
- USB/TTL serial connection
- six servo motors driving six tendons
- two-joint rope-driven soft robot motion response

`src/Gradua` contains a ROS package and should be treated as a future improvement reserve,
not as a current architecture requirement.

When inspecting code, always identify:
- how visual results are converted into controllable error variables
- how error variables are mapped to servo IDs, tendon actions, or joint-level control quantities
- what safety limits exist for servo command size, rate, and coordination
- whether the current code is truly closed-loop or only computes visual offsets without actuator execution

## Vision assumptions

Current validation hardware uses a single USB camera.
Therefore:
- do not assume a full stereo 3D perception stack unless explicitly provided
- image coordinates may be the main visual input
- PBVS-like ideas or hybrid methods may still be discussed,
  but implementation must match actual sensing availability

## Control assumptions

The actuator system is currently closer to a rope-driven soft robot than to a general-purpose rigid manipulator.

Therefore:
- do not default to standard industrial arm templates
- do not introduce full manipulator planning stacks unless necessary
- respect the coupling between visual error, tendon actuation, and soft-body deformation
- prefer practical mappings from image error to six-servo control quantities that are easy to test and revise

## Output behavior

When asked to modify code:
- first explain the current structure briefly
- then state what is missing or broken
- then propose the smallest effective set of changes
- then output code with comments
- mention any assumptions clearly

When asked to write thesis-related material:
- give academically reasonable suggestions
- keep style natural, not formulaically AI-like
- distinguish clearly between:
  background,
  related work,
  method design,
  system implementation,
  experiments,
  limitations,
  and future work
- avoid fabricating citations or pretending to have read papers that were not actually available

## Preferred behavior for uncertain cases

If requirements are ambiguous:
- do not invent hardware capabilities
- do not assume ROS2 or STM32 are part of the current implementation unless explicitly requested
- do not claim an experiment has been validated if only code-level reasoning was performed

Instead:
- make the most conservative technically valid assumption
- say what assumption was made
- keep the solution easy to revise later
