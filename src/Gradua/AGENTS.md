## Preferred code style

When generating or modifying code in this repository, follow this style by default:

1. Prefer object-oriented structure where appropriate, especially for ROS2 nodes, controllers, and processing modules.
2. Each file should have a clear single responsibility. Avoid mixing unrelated logic in one module.
3. Prefer concise and efficient implementations. Do not add unnecessary abstraction, wrappers, or overly complex design patterns.
4. Keep the main execution path clear: initialization, subscriptions/publications, core processing, cleanup.
5. Class, function, variable, topic, and parameter names must be clear and engineering-oriented. Avoid vague names.
6. New code should preserve the project’s existing practical style: readable, direct, maintainable, and easy to debug.
7. Comments must be written in Chinese.
8. Comments should explain:
   - the purpose of the file
   - the responsibility of each class
   - the purpose, inputs, and outputs of each function
   - the intent of key logic blocks
   - the meaning of important states, flags, and parameters
9. Comments should be concise and natural. Avoid tutorial-style filler and avoid mechanically restating obvious code.
10. For ROS2 Python code, prefer a clean class-based node structure similar to:
    - one main node class
    - clear callback methods
    - explicit resource initialization and cleanup
    - simple and readable main entry
11. Prefer minimum necessary modification when editing existing code. Do not rewrite working structure without clear reason.
12. Code should look like real project code, not like a generic demo or overly polished AI-generated template.