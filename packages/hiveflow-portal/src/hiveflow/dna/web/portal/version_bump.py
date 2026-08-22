"""Shared governance version bump field markup and client script."""

from __future__ import annotations

from html import escape


def version_bump_field_html(
    *,
    input_id: str,
    input_name: str,
    label: str,
    value: str,
    base_version: str,
    next_patch: str,
    next_minor: str,
    next_major: str,
    field_class: str = "form-field",
) -> str:
    """Read-only next-patch version input with minor/major bump buttons."""
    return f"""
            <div class="{escape(field_class)}" data-version-bump
              data-base-version="{escape(base_version)}"
              data-next-patch="{escape(next_patch)}"
              data-next-minor="{escape(next_minor)}"
              data-next-major="{escape(next_major)}">
              <label for="{escape(input_id)}">{escape(label)}</label>
              <div class="version-bump-row">
                <input id="{escape(input_id)}" name="{escape(input_name)}"
                  value="{escape(value)}" required readonly
                  pattern="\\d+\\.\\d+\\.\\d+" title="Semver major.minor.patch"
                  data-version-input />
                <div class="version-bump-buttons">
                  <button type="button" class="btn version-bump-btn" data-bump="minor"
                    title="Bump to v{escape(next_minor)}">Minor</button>
                  <button type="button" class="btn version-bump-btn" data-bump="major"
                    title="Bump to v{escape(next_major)}">Major</button>
                </div>
              </div>
              <p class="form-hint">
                Defaults to the next patch (<code>v{escape(next_patch)}</code>).
                Use Minor (<code>v{escape(next_minor)}</code>) or Major
                (<code>v{escape(next_major)}</code>) to bump; patch/minor reset accordingly.
              </p>
              <p class="form-warning" data-version-warning hidden></p>
            </div>
    """


def version_bump_script() -> str:
    return """
<script>
(function () {
  function classify(root, proposed) {
    var base = (root.getAttribute("data-base-version") || "").trim();
    var nextPatch = (root.getAttribute("data-next-patch") || "").trim();
    var nextMinor = (root.getAttribute("data-next-minor") || "").trim();
    var nextMajor = (root.getAttribute("data-next-major") || "").trim();
    proposed = (proposed || "").trim();
    if (!proposed) return { kind: "invalid", text: "" };
    if (proposed === nextPatch) return { kind: "patch", text: "" };
    if (proposed === nextMinor) {
      var minorLine = proposed.split(".").slice(0, 2).join(".");
      return {
        kind: "minor",
        text: "Minor bump from v" + base + " to v" + proposed +
          ": patch resets to 0, and all further versions will continue from v" +
          minorLine + ".x."
      };
    }
    if (proposed === nextMajor) {
      var majorLine = proposed.split(".")[0];
      return {
        kind: "major",
        text: "Major bump from v" + base + " to v" + proposed +
          ": minor and patch reset to 0, and all further versions will continue from v" +
          majorLine + ".x.x."
      };
    }
    return {
      kind: "invalid",
      text: "Use the next patch (" + nextPatch + "), next minor (" + nextMinor +
        "), or next major (" + nextMajor + ")."
    };
  }

  function refresh(root) {
    var input = root.querySelector("[data-version-input]");
    var warning = root.querySelector("[data-version-warning]");
    if (!input || !warning) return;
    var result = classify(root, input.value);
    warning.hidden = !result.text;
    warning.textContent = result.text;
    warning.classList.toggle("form-warning", result.kind === "minor" || result.kind === "major");
    warning.classList.toggle("form-error", result.kind === "invalid");
    root.querySelectorAll("[data-bump]").forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-bump") === result.kind);
    });
  }

  function bind(root) {
    if (root.getAttribute("data-version-bump-bound") === "1") return;
    root.setAttribute("data-version-bump-bound", "1");
    var input = root.querySelector("[data-version-input]");
    if (!input) return;
    var nextPatch = (root.getAttribute("data-next-patch") || "").trim();
    var nextMinor = (root.getAttribute("data-next-minor") || "").trim();
    var nextMajor = (root.getAttribute("data-next-major") || "").trim();
    root.querySelectorAll("[data-bump]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var kind = btn.getAttribute("data-bump");
        var target = kind === "minor" ? nextMinor : nextMajor;
        if ((input.value || "").trim() === target) {
          input.value = nextPatch;
        } else {
          input.value = target;
        }
        refresh(root);
      });
    });
    var form = root.closest("form");
    if (form && form.getAttribute("data-version-bump-submit") !== "1") {
      form.setAttribute("data-version-bump-submit", "1");
      form.addEventListener("submit", function (event) {
        var submitter = event.submitter;
        var action = submitter ? (submitter.getAttribute("value") || "") : "";
        if (action === "reject" || action.indexOf("deny") === 0) return;
        var fields = form.querySelectorAll("[data-version-bump]");
        for (var i = 0; i < fields.length; i++) {
          var field = fields[i];
          var fieldInput = field.querySelector("[data-version-input]");
          if (!fieldInput) continue;
          var result = classify(field, fieldInput.value);
          if (result.kind === "invalid") {
            event.preventDefault();
            refresh(field);
            fieldInput.focus();
            return;
          }
          if ((result.kind === "minor" || result.kind === "major") &&
              !window.confirm(result.text + "\\n\\nContinue with this version?")) {
            event.preventDefault();
            return;
          }
        }
      });
    }
    refresh(root);
  }

  function bindAll(scope) {
    (scope || document).querySelectorAll("[data-version-bump]").forEach(bind);
  }

  bindAll(document);
  document.addEventListener("hiveflow:assistant-live-updated", function (event) {
    bindAll((event && event.target) || document);
  });
})();
</script>
"""
