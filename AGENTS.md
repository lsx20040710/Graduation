# AGENTS.md

## Project identity

This repository is for an undergraduate thesis project:
"Visual servo control for a retractable suction device on a sea cucumber harvesting robot".

The core of this project is NOT a generic object detection demo,
NOT a full AUV autonomy project,
and NOT a standard 6-DOF industrial manipulator project.

The project should always be understood as:
a vision-servo control system for a retractable suction end-effector
used in underwater sea cucumber harvesting.

## Primary goals

When analyzing, modifying, or generating code, always prioritize:

1. Building or improving a closed-loop pipeline:
   visual detection -> target information -> servo control -> actuator command -> execution feedback

2. Preserving project structure and existing module boundaries whenever possible

3. Making the system runnable, debuggable, and easy to integrate

4. Ensuring the code fits the kinematic and control characteristics of a retractable suction device,
   rather than assuming a traditional rigid industrial robot arm

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

## ROS2 / control understanding

This project uses a layered architecture.

Top layer:
- ROS2 nodes for vision, target message publishing, servo logic, and command dispatch

Bottom layer:
- hardware execution for retractable actuation and suction-device-related motion control

When inspecting code, always identify:
- node input/output relationships
- how visual results are passed into control
- what the controller outputs (position, velocity, PWM, displacement, etc.)
- where upper-lower layer interfaces are
- whether the current code is truly closed-loop or only partially connected

## Vision assumptions

Current validation hardware may use a single USB camera.
Therefore:
- do not assume a full stereo 3D perception stack unless explicitly provided
- image coordinates may be the main visual input
- PBVS-like ideas or hybrid methods may still be discussed,
  but implementation must match actual sensing availability

## Control assumptions

The actuator is closer to a retractable / small-range pose-adjustment mechanism
than to a general-purpose 6-DOF manipulator.

Therefore:
- do not default to standard industrial arm templates
- do not introduce full manipulator planning stacks unless necessary
- respect the coupling between visual error and retractable actuator motion

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
- do not assume unavailable sensors or actuators
- do not claim an experiment has been validated if only code-level reasoning was performed

Instead:
- make the most conservative technically valid assumption
- say what assumption was made
- keep the solution easy to revise later