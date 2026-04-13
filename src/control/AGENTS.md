# Control-code local rules

Prefer:
- explicit signal flow
- bounded control outputs
- readable callback logic
- clear separation between perception input, control computation, and actuator output

Avoid:
- giant all-in-one nodes
- hidden global state
- magic numbers without comments
- copying formulas without explaining variable meaning