document.addEventListener("DOMContentLoaded", function () {
  var DBC_LOOKUP_FIELDS = [
    "BC_CLIENT_ID",
    "BC_CLIENT_SECRET",
    "BC_TENANT_ID",
    "BC_ENVIRONMENT_NAME",
  ];
  var DBC_LOAD_DISABLED_TITLE =
    "Fill in the four fields above (Entra client id, client secret, tenant id, and BC environment name) to load companies.";
  var DBC_LOAD_ENABLED_TITLE = "Load companies from this BC environment";

  function dbcLookupFieldsReady(form) {
    return DBC_LOOKUP_FIELDS.every(function (key) {
      var input = form.querySelector('[name="' + key + '"]');
      return input && String(input.value || "").trim();
    });
  }

  function syncDbcLoadCompaniesButton(form) {
    var loadBtn = form.querySelector("[data-dbc-load-companies]");
    if (!loadBtn) return;
    var ready = dbcLookupFieldsReady(form);
    loadBtn.disabled = !ready;
    loadBtn.title = ready ? DBC_LOAD_ENABLED_TITLE : DBC_LOAD_DISABLED_TITLE;
  }

  function bindDbcLoadCompaniesForm(form) {
    if (!form.getAttribute("data-dbc-companies-url")) return;
    syncDbcLoadCompaniesButton(form);
    DBC_LOOKUP_FIELDS.forEach(function (key) {
      var input = form.querySelector('[name="' + key + '"]');
      if (!input) return;
      input.addEventListener("input", function () {
        syncDbcLoadCompaniesButton(form);
      });
      input.addEventListener("change", function () {
        syncDbcLoadCompaniesButton(form);
      });
    });
  }

  function setConnectorValidated(validateBtn, isValidated) {
    if (!validateBtn) return;
    var check = validateBtn.querySelector("[data-connector-validate-check]");
    var label = validateBtn.querySelector("[data-connector-validate-label]");
    if (isValidated) {
      validateBtn.classList.add("is-validated");
      if (check) check.setAttribute("aria-hidden", "false");
      if (label) label.textContent = "Validated";
      return;
    }
    validateBtn.classList.remove("is-validated");
    if (check) check.setAttribute("aria-hidden", "true");
    if (label) label.textContent = "Validate connector";
  }

  function resetConnectorValidateState(form) {
    var validateBtn = form.querySelector("[data-connector-validate]");
    if (!validateBtn) return;
    setConnectorValidated(validateBtn, false);
    validateBtn.disabled = false;
    var status = form.querySelector("[data-connector-validate-status]");
    if (status) {
      status.hidden = true;
      status.textContent = "";
      status.classList.remove("is-error", "is-ok");
    }
    syncContinueDeployButton();
  }

  function allConnectorsValidated() {
    var shell = document.querySelector("[data-onboarding-connectors]");
    if (!shell) return true;
    var expected = parseInt(shell.getAttribute("data-connector-count") || "0", 10);
    var validated = shell.querySelectorAll("[data-connector-validate].is-validated").length;
    if (!expected) return validated > 0;
    return validated >= expected;
  }

  function syncContinueDeployButton() {
    var shell = document.querySelector("[data-onboarding-connectors]");
    if (!shell) return;
    var continueBtn = shell.querySelector("[data-connector-continue-deploy]");
    var hint = shell.querySelector("[data-connector-continue-hint]");
    var ready = allConnectorsValidated();
    if (continueBtn) {
      continueBtn.classList.toggle("is-disabled", !ready);
      continueBtn.setAttribute("aria-disabled", ready ? "false" : "true");
    }
    if (hint) {
      hint.textContent = ready
        ? "All connectors validated. Continue to deploy stacks."
        : "Validate every connector above to continue.";
    }
  }

  function bindConnectorValidateForm(form) {
    form.querySelectorAll("[data-credential-main], [name]").forEach(function (input) {
      if (!input.name || input.type === "hidden") return;
      input.addEventListener("input", function () {
        resetConnectorValidateState(form);
      });
      input.addEventListener("change", function () {
        resetConnectorValidateState(form);
      });
    });
  }

  document.querySelectorAll("form[data-connector-validate-url]").forEach(bindConnectorValidateForm);
  document.querySelectorAll("form[data-dbc-companies-url]").forEach(bindDbcLoadCompaniesForm);

  function setMainCredentialValue(form, key, value) {
    var main = form.querySelector('[data-credential-main="' + key + '"]');
    if (!main) return;
    if (main.tagName === "SELECT") {
      var found = false;
      var index;
      for (index = 0; index < main.options.length; index += 1) {
        if (main.options[index].value === value) {
          found = true;
          break;
        }
      }
      if (!found && value) {
        var option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        main.appendChild(option);
      }
      main.value = value || "";
      main.disabled = !value && main.options.length <= 1;
      return;
    }
    main.value = value;
    syncDbcLoadCompaniesButton(form);
  }

  function syncGuideToMain(dialog) {
    var form = dialog.closest("form");
    if (!form) return;
    dialog.querySelectorAll("[data-credential-guide]").forEach(function (guideInput) {
      var key = guideInput.getAttribute("data-credential-guide");
      if (!key) return;
      setMainCredentialValue(form, key, guideInput.value);
    });
  }

  function syncMainToGuide(dialog) {
    var form = dialog.closest("form");
    if (!form) return;
    dialog.querySelectorAll("[data-credential-guide]").forEach(function (guideInput) {
      var key = guideInput.getAttribute("data-credential-guide");
      if (!key) return;
      var mainInput = form.querySelector('[data-credential-main="' + key + '"]');
      if (mainInput) {
        guideInput.value = mainInput.value;
      }
    });
  }

  document.querySelectorAll(".admin-connector-guide-dialog").forEach(function (dialog) {
    dialog.addEventListener("close", function () {
      syncGuideToMain(dialog);
    });
  });

  document.addEventListener("submit", function (event) {
    var submitter = event.submitter;
    if (submitter && submitter.hasAttribute("data-connector-validate")) {
      event.preventDefault();
    }
  });

  document.addEventListener("click", function (event) {
    var validateBtn = event.target && event.target.closest
      ? event.target.closest("[data-connector-validate]")
      : null;
    if (validateBtn) {
      event.preventDefault();
      var form = validateBtn.closest("form");
      if (!form || validateBtn.disabled) return;
      var validateUrl = form.getAttribute("data-connector-validate-url");
      if (!validateUrl) return;
      var status = form.querySelector("[data-connector-validate-status]");
      var label = validateBtn.querySelector("[data-connector-validate-label]");
      setConnectorValidated(validateBtn, false);
      if (label) label.textContent = "Validating…";
      if (status) {
        status.hidden = false;
        status.textContent = "Validating connector…";
        status.classList.remove("is-error", "is-ok");
      }
      validateBtn.disabled = true;
      fetch(validateUrl, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-Meshflow-Inline": "1",
        },
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            return { ok: response.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (!result.ok || !result.payload.ok) {
            throw new Error(result.payload.message || result.payload.error || "Validation failed.");
          }
          setConnectorValidated(validateBtn, true);
          if (status) {
            status.hidden = false;
            status.textContent = result.payload.message || "Connector validated.";
            status.classList.add("is-ok");
            status.classList.remove("is-error");
          }
          syncContinueDeployButton();
        })
        .catch(function (error) {
          setConnectorValidated(validateBtn, false);
          if (status) {
            status.hidden = false;
            status.textContent = error && error.message ? error.message : "Validation failed.";
            status.classList.add("is-error");
            status.classList.remove("is-ok");
          }
          syncContinueDeployButton();
        })
        .finally(function () {
          validateBtn.disabled = false;
        });
      return;
    }

    var loadBtn = event.target && event.target.closest
      ? event.target.closest("[data-dbc-load-companies]")
      : null;
    if (loadBtn) {
      var loadForm = loadBtn.closest("form");
      if (!loadForm || loadBtn.disabled) return;
      var companiesUrl = loadForm.getAttribute("data-dbc-companies-url");
      if (!companiesUrl) return;
      var companyStatus = loadForm.querySelector("[data-dbc-company-status]");
      var select = loadForm.querySelector('[data-credential-main="BC_COMPANY_ID"]');
      if (!select) return;
      var body = new FormData();
      DBC_LOOKUP_FIELDS.forEach(function (key) {
        var input = loadForm.querySelector('[name="' + key + '"]');
        if (input) body.append(key, input.value);
      });
      if (companyStatus) {
        companyStatus.hidden = false;
        companyStatus.textContent = "Loading companies…";
      }
      loadBtn.disabled = true;
      fetch(companiesUrl, {
        method: "POST",
        body: body,
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-Meshflow-Inline": "1",
        },
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            return { ok: response.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (!result.ok || !result.payload.ok) {
            throw new Error(result.payload.error || "Unable to load companies.");
          }
          var selected = select.value;
          select.innerHTML = "";
          var placeholder = document.createElement("option");
          placeholder.value = "";
          placeholder.textContent = "Select a company…";
          select.appendChild(placeholder);
          result.payload.companies.forEach(function (company) {
            var option = document.createElement("option");
            option.value = company.id;
            option.textContent = company.display_name + " (" + company.id + ")";
            select.appendChild(option);
          });
          select.disabled = false;
          if (selected) {
            select.value = selected;
          }
          if (companyStatus) {
            companyStatus.textContent =
              result.payload.companies.length + " companies loaded. Select one, then validate or save.";
          }
        })
        .catch(function (error) {
          if (companyStatus) {
            companyStatus.textContent = error && error.message ? error.message : "Unable to load companies.";
          }
        })
        .finally(function () {
          syncDbcLoadCompaniesButton(loadForm);
        });
      return;
    }

    var openBtn = event.target && event.target.closest
      ? event.target.closest("[data-connector-guide]")
      : null;
    if (openBtn) {
      var openId = openBtn.getAttribute("data-connector-guide");
      if (openId) {
        var openDialog = document.getElementById(openId);
        if (openDialog && typeof openDialog.showModal === "function") {
          syncMainToGuide(openDialog);
          openDialog.showModal();
        }
      }
      return;
    }

    var applyBtn = event.target && event.target.closest
      ? event.target.closest("[data-connector-guide-apply]")
      : null;
    if (applyBtn) {
      var applyId = applyBtn.getAttribute("data-connector-guide-apply");
      if (applyId) {
        var applyDialog = document.getElementById(applyId);
        if (applyDialog) {
          syncGuideToMain(applyDialog);
          if (typeof applyDialog.close === "function") {
            applyDialog.close();
          }
        }
      }
      return;
    }

    var continueBtn = event.target && event.target.closest
      ? event.target.closest("[data-connector-continue-deploy]")
      : null;
    if (continueBtn) {
      if (continueBtn.classList.contains("is-disabled")) {
        event.preventDefault();
      }
      return;
    }

    var closeBtn = event.target && event.target.closest
      ? event.target.closest("[data-connector-guide-close]")
      : null;
    if (!closeBtn) return;
    var closeId = closeBtn.getAttribute("data-connector-guide-close");
    if (!closeId) return;
    var closeDialog = document.getElementById(closeId);
    if (closeDialog) {
      syncGuideToMain(closeDialog);
      if (typeof closeDialog.close === "function") {
        closeDialog.close();
      }
    }
  });

  var STACK_POLL_MS = 30000;
  var STACK_ACTIVE = { in_progress: true };

  function stackCssFor(status) {
    var key = String(status || "unknown").toLowerCase().replace(/_/g, " ");
    if (key.indexOf("complete") >= 0 || key.indexOf("ok") >= 0 || key.indexOf("success") >= 0) {
      return "is-ok";
    }
    if (
      key.indexOf("progress") >= 0 ||
      key.indexOf("pending") >= 0 ||
      key.indexOf("running") >= 0 ||
      key.indexOf("queued") >= 0
    ) {
      return "is-running";
    }
    if (key.indexOf("fail") >= 0 || key.indexOf("error") >= 0 || key.indexOf("rollback") >= 0) {
      return "is-error";
    }
    return "is-unknown";
  }

  function stackLabelFor(status) {
    return String(status || "unknown")
      .replace(/_/g, " ")
      .replace(/\b\w/g, function (letter) {
        return letter.toUpperCase();
      });
  }

  function stackProgressState(status) {
    var key = String(status || "unknown").toLowerCase();
    if (key === "complete") return "is-complete";
    if (key === "failed") return "is-error";
    if (key === "in_progress") return "is-indeterminate";
    return "is-idle";
  }

  function stackProgressWidth(status) {
    var key = String(status || "unknown").toLowerCase();
    if (key === "complete" || key === "failed") return 100;
    if (key === "not_found") return 0;
    if (key === "in_progress") return null;
    return 8;
  }

  function applyStackRow(row, item) {
    var status = String((item && item.status) || "unknown");
    row.setAttribute("data-stack-status", status);
    var badge = row.querySelector("[data-stack-status-badge]");
    if (badge) {
      badge.className = "admin-job-state " + stackCssFor(status);
      badge.textContent = stackLabelFor(status);
    }
    var reason = row.querySelector("[data-stack-reason]");
    if (reason) {
      reason.textContent = String((item && item.status_reason) || "");
    }
    var progress = row.querySelector("[data-stack-progress]");
    var bar = row.querySelector("[data-stack-progress-bar]");
    if (!progress || !bar) return;
    var width = stackProgressWidth(status);
    progress.className = "admin-stack-progress " + stackProgressState(status);
    if (width === null) {
      bar.style.width = "";
    } else {
      bar.style.width = String(width) + "%";
    }
  }

  function applyStackPayload(section, payload) {
    var stacks = payload && payload.deploy && payload.deploy.stacks;
    if (!Array.isArray(stacks)) return false;
    stacks.forEach(function (item) {
      var stackName = String((item && item.stack_name) || "");
      if (!stackName) return;
      var row = section.querySelector('[data-stack-row][data-stack-name="' + stackName + '"]');
      if (row) applyStackRow(row, item);
    });
    return true;
  }

  function sectionHasActiveStacks(section) {
    return Array.from(section.querySelectorAll("[data-stack-row]")).some(function (row) {
      return !!STACK_ACTIVE[String(row.getAttribute("data-stack-status") || "").toLowerCase()];
    });
  }

  function setDeployStatusMessage(section, message, active) {
    var statusEl = section.querySelector("[data-stack-deploy-status]");
    if (!statusEl) return;
    var text = String(message || "").trim();
    if (!text) {
      statusEl.hidden = true;
      statusEl.textContent = "";
      statusEl.classList.remove("is-active");
      return;
    }
    statusEl.hidden = false;
    statusEl.textContent = text;
    statusEl.classList.toggle("is-active", !!active);
  }

  function setStatusUrlBuildId(section, buildId) {
    var statusUrl = section.getAttribute("data-stack-status-url") || "";
    if (!statusUrl) return;
    var parsed = new URL(statusUrl, window.location.href);
    if (buildId) {
      parsed.searchParams.set("build_id", buildId);
    } else {
      parsed.searchParams.delete("build_id");
    }
    section.setAttribute("data-stack-status-url", parsed.pathname + parsed.search);
  }

  function refreshStackStatus(section) {
    var statusUrl = section.getAttribute("data-stack-status-url");
    if (!statusUrl) return Promise.resolve(false);
    return fetch(statusUrl, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) return false;
        return response.json().then(function (payload) {
          applyStackPayload(section, payload);
          var build = payload && payload.build;
          if (build && build.status) {
            section.setAttribute("data-stack-build-id", String(build.build_id || ""));
            var buildStatus = String(build.status || "").toLowerCase();
            if (buildStatus === "in_progress") {
              section.setAttribute("data-stack-build-active", "1");
              setDeployStatusMessage(
                section,
                "CodeBuild " + String(build.current_phase || "running") + "…",
                true
              );
            } else {
              section.removeAttribute("data-stack-build-active");
              if (buildStatus === "succeeded") {
                setDeployStatusMessage(section, "CodeBuild finished successfully.", false);
              } else if (buildStatus === "failed") {
                setDeployStatusMessage(section, "CodeBuild failed. Check CloudWatch logs.", false);
              }
            }
          }
          return sectionHasActiveStacks(section);
        });
      })
      .catch(function () {
        return sectionHasActiveStacks(section);
      });
  }

  function startStackPolling(section) {
    if (!section || section.getAttribute("data-stack-polling") === "1") return;
    section.setAttribute("data-stack-polling", "1");
    var pollMs = parseInt(section.getAttribute("data-stack-poll-ms") || String(STACK_POLL_MS), 10);
    if (!pollMs || pollMs < 1000) pollMs = STACK_POLL_MS;

    function scheduleNext(active) {
      window.setTimeout(tick, pollMs);
    }

    function tick() {
      refreshStackStatus(section).then(function (active) {
        var buildActive = section.getAttribute("data-stack-build-active") === "1";
        if (active || buildActive) {
          scheduleNext(active);
        } else {
          section.removeAttribute("data-stack-polling");
        }
      });
    }

    refreshStackStatus(section).then(function () {
      window.setTimeout(tick, pollMs);
    });
  }

  document.querySelectorAll("[data-stack-status-section]").forEach(function (section) {
    var deployForm = section.querySelector("[data-stack-deploy-form]");
    if (deployForm) {
      deployForm.addEventListener("submit", function (event) {
        event.preventDefault();
        var deployBtn = deployForm.querySelector("[data-stack-deploy-btn]");
        if (deployBtn) deployBtn.disabled = true;
        setDeployStatusMessage(section, "Starting deploy…", true);
        fetch(deployForm.action, {
          method: "POST",
          body: new FormData(deployForm),
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "X-Meshflow-Inline": "1",
          },
        })
          .then(function (response) {
            return response.json().then(function (payload) {
              return { ok: response.ok, payload: payload };
            });
          })
          .then(function (result) {
            if (!result.ok || !result.payload.ok) {
              throw new Error(result.payload.message || result.payload.error || "Deploy failed.");
            }
            var buildId = String(result.payload.build_id || "");
            if (buildId) {
              section.setAttribute("data-stack-build-id", buildId);
              setStatusUrlBuildId(section, buildId);
            }
            setDeployStatusMessage(
              section,
              result.payload.message || "Deploy started. Refreshing stack status every 30 seconds…",
              true
            );
            section.setAttribute("data-stack-build-active", "1");
            section.removeAttribute("data-stack-polling");
            startStackPolling(section);
          })
          .catch(function (error) {
            setDeployStatusMessage(
              section,
              error && error.message ? error.message : "Deploy failed.",
              false
            );
          })
          .finally(function () {
            if (deployBtn) deployBtn.disabled = false;
          });
      });
    }

    var buildId = section.getAttribute("data-stack-build-id") || "";
    if (sectionHasActiveStacks(section) || buildId) {
      if (buildId) {
        section.setAttribute("data-stack-build-active", "1");
      }
      startStackPolling(section);
    }
  });

  syncContinueDeployButton();
});
