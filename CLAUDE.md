<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## Claude Code Guidelines / Guía para Claude Code

This file provides operational guidance for Claude Code (claude.ai/code) when working within this repository.

---

# 🇺🇸 English Version

## Working Principles

- Think before acting. Understand the context and architecture before making changes.
- Read related files before writing or modifying code.
- Modify only what is necessary. Avoid rewriting entire files unless explicitly required.
- Do not re-read files already analyzed unless they have changed.
- Keep diffs minimal, clean, and intentional.
- Preserve existing project structure, naming conventions, and patterns.
- Prioritize maintainability, readability, and performance.

## Code Standards

- Avoid duplicated logic whenever possible.
- Reuse existing services, helpers, components, traits, composables, and utilities.
- Do not introduce unnecessary abstractions or premature optimizations.
- Prefer explicit and predictable code over “magic” solutions.
- Keep methods and classes focused on a single responsibility.
- Respect SOLID principles when applicable.
- Maintain backward compatibility unless instructed otherwise.

## Response Rules

- Do not repeat unchanged code in responses.
- Do not explain obvious changes.
- No unnecessary introductions or closing summaries.
- Keep responses concise, technical, and actionable.
- Show only relevant snippets when possible.

## Testing & Validation

- Validate changes before considering the task complete.
- Run existing tests whenever applicable.
- Check for syntax, linting, type, and formatting errors.
- Ensure no regressions are introduced.
- Verify imports, dependencies, and affected integrations.

## Frontend & UI

- Prefer Tailwind CSS for styling.
- Use clean, modern, and accessible UI patterns.
- Avoid inline styles unless strictly necessary.
- Use professional icons instead of emojis.
- Maintain responsive and consistent layouts.
- Respect existing design systems and component conventions.

## Git & Repository Hygiene

- Keep commits focused and atomic.
- Avoid unrelated changes in the same commit.
- Never modify generated, compiled, or vendor files unless required.
- Respect `.gitignore`, environment separation, and repository standards.

---

# 🇪🇸 Versión en Español

## Principios de Trabajo

- Piensa antes de actuar. Comprende el contexto y la arquitectura antes de realizar cambios.
- Lee los archivos relacionados antes de escribir o modificar código.
- Modifica únicamente lo necesario. Evita reescribir archivos completos salvo que sea estrictamente necesario.
- No releas archivos ya analizados, excepto si han cambiado.
- Mantén los diffs mínimos, limpios e intencionales.
- Conserva la estructura, convenciones y patrones existentes del proyecto.
- Prioriza mantenibilidad, legibilidad y rendimiento.

## Estándares de Código

- Evita lógica duplicada siempre que sea posible.
- Reutiliza servicios, helpers, componentes, traits, composables y utilidades existentes.
- No introduzcas abstracciones innecesarias ni optimizaciones prematuras.
- Prefiere código explícito y predecible sobre soluciones “mágicas”.
- Mantén métodos y clases enfocados en una única responsabilidad.
- Respeta principios SOLID cuando aplique.
- Mantén compatibilidad hacia atrás salvo que se indique lo contrario.

## Reglas de Respuesta

- No repitas código sin cambios en las respuestas.
- No expliques cambios obvios.
- Sin introducciones innecesarias ni resúmenes finales.
- Mantén respuestas concisas, técnicas y accionables.
- Muestra únicamente fragmentos relevantes cuando sea posible.

## Testing y Validación

- Valida los cambios antes de dar una tarea por finalizada.
- Ejecuta pruebas existentes cuando aplique.
- Verifica errores de sintaxis, linting, tipado y formato.
- Asegura que no existan regresiones.
- Verifica imports, dependencias e integraciones afectadas.

## Frontend y UI

- Prioriza Tailwind CSS para estilos.
- Usa patrones de UI modernos, limpios y accesibles.
- Evita estilos inline salvo que sea estrictamente necesario.
- Usa iconos profesionales en lugar de emojis.
- Mantén layouts responsivos y consistentes.
- Respeta el sistema de diseño y convenciones existentes.

## Git y Buenas Prácticas del Repositorio

- Mantén commits enfocados y atómicos.
- Evita cambios no relacionados en el mismo commit.
- No modifiques archivos generados, compilados o vendor salvo que sea necesario.
- Respeta `.gitignore`, separación de entornos y estándares del repositorio.
