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
          "X-HiveFlow-Inline": "1",
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
          "X-HiveFlow-Inline": "1",
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
  var STACK_ACTIVE_POLL_MS = 10000;
  var STACK_ACTIVE = { in_progress: true };
  var BUILD_ACTIVE = { in_progress: true };

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

  function markAllStacksInProgress(section, reason) {
    Array.from(section.querySelectorAll("[data-stack-row]")).forEach(function (row) {
      applyStackRow(row, {
        status: "in_progress",
        status_reason: reason || "CodeBuild deploy in progress…",
      });
    });
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
            if (BUILD_ACTIVE[buildStatus]) {
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
      var delay = section.getAttribute("data-stack-build-active") === "1" ? STACK_ACTIVE_POLL_MS : pollMs;
      window.setTimeout(tick, delay);
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
            "X-HiveFlow-Inline": "1",
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
            markAllStacksInProgress(section, "CodeBuild deploy starting…");
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

  var PIPELINE_ACTIVE = { running: true, pending_redrive: true };
  var PIPELINE_POLL_MS = 10000;

  function pipelineCssFor(status) {
    return stackCssFor(status);
  }

  function pipelineLabelFor(status) {
    return stackLabelFor(status);
  }

  function setPipelineActionStatus(section, message, active) {
    var statusEl = section.querySelector("[data-pipeline-action-status]");
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

  function applyPipelineRow(row, payload) {
    if (!row || !payload) return;
    var status = String(payload.status || "not_started");
    row.setAttribute("data-pipeline-status", status);
    row.setAttribute("data-pipeline-execution", String(payload.execution_arn || ""));
    row.setAttribute("data-pipeline-has-report", payload.has_report ? "1" : "0");
    var badge = row.querySelector("[data-pipeline-status-badge]");
    if (badge) {
      badge.className = "admin-job-state " + pipelineCssFor(status);
      badge.textContent = pipelineLabelFor(status);
    }
    var note = row.querySelector("[data-pipeline-note]");
    if (note && payload.note) {
      note.textContent = String(payload.note);
    }
    var execution = row.querySelector("[data-pipeline-execution]");
    var executionLabel = row.querySelector("[data-pipeline-execution-label]");
    if (execution && executionLabel) {
      var arn = String(payload.execution_arn || "");
      if (arn) {
        execution.hidden = false;
        executionLabel.textContent = arn;
      } else {
        execution.hidden = true;
        executionLabel.textContent = "";
      }
    }
    var reportBtn = row.querySelector("[data-ingest-report-open]");
    if (reportBtn) {
      reportBtn.hidden = !payload.has_report;
    } else if (payload.has_report && row.getAttribute("data-pipeline-key") !== "dna") {
      var actions = row.querySelector(".admin-onboarding-actions");
      if (actions) {
        var connector = row.getAttribute("data-pipeline-key") || "";
        var button = document.createElement("button");
        button.type = "button";
        button.className = "btn secondary";
        button.setAttribute("data-ingest-report-open", "");
        button.setAttribute("data-ingest-report-connector", connector);
        button.textContent = "View ingest report";
        actions.appendChild(button);
      }
    }
  }

  function trackedExecutionParams(section) {
    var params = new URLSearchParams();
    section.querySelectorAll("[data-pipeline-row]").forEach(function (row) {
      var key = row.getAttribute("data-pipeline-key") || "";
      var execution = row.getAttribute("data-pipeline-execution") || "";
      if (!execution) return;
      if (key === "dna") {
        params.set("dna_execution", execution);
      } else {
        params.set("ingest_" + key, execution);
      }
    });
    return params;
  }

  function sectionHasActivePipelines(section) {
    return Array.from(section.querySelectorAll("[data-pipeline-row]")).some(function (row) {
      var status = String(row.getAttribute("data-pipeline-status") || "").toLowerCase();
      return !!PIPELINE_ACTIVE[status];
    });
  }

  function refreshPipelineStatus(section) {
    var statusUrl = section.getAttribute("data-pipeline-status-url");
    if (!statusUrl) return Promise.resolve(false);
    var parsed = new URL(statusUrl, window.location.href);
    var tracked = trackedExecutionParams(section);
    tracked.forEach(function (value, key) {
      parsed.searchParams.set(key, value);
    });
    return fetch(parsed.pathname + parsed.search, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) return false;
        return response.json().then(function (payload) {
          var ingest = payload && payload.ingest;
          if (ingest && typeof ingest === "object") {
            Object.keys(ingest).forEach(function (connector) {
              var row = section.querySelector(
                '[data-pipeline-row][data-pipeline-key="' + connector + '"]'
              );
              applyPipelineRow(row, ingest[connector]);
            });
          }
          var dna = payload && payload.dna;
          if (dna && typeof dna === "object") {
            var dnaRow = section.querySelector('[data-pipeline-row][data-pipeline-key="dna"]');
            applyPipelineRow(dnaRow, dna);
          }
          return sectionHasActivePipelines(section);
        });
      })
      .catch(function () {
        return sectionHasActivePipelines(section);
      });
  }

  function startPipelinePolling(section) {
    if (!section || section.getAttribute("data-pipeline-polling") === "1") return;
    section.setAttribute("data-pipeline-polling", "1");

    function tick() {
      refreshPipelineStatus(section).then(function (active) {
        if (active) {
          window.setTimeout(tick, PIPELINE_POLL_MS);
        } else {
          section.removeAttribute("data-pipeline-polling");
        }
      });
    }

    refreshPipelineStatus(section).then(function (active) {
      if (active) {
        window.setTimeout(tick, PIPELINE_POLL_MS);
      } else {
        section.removeAttribute("data-pipeline-polling");
      }
    });
  }

  function renderIngestReportHtml(report) {
    var tables = Array.isArray(report.tables) ? report.tables : [];
    var rows = tables
      .map(function (item) {
        return (
          "<tr><td>" +
          String(item.table || "") +
          "</td><td>" +
          String(item.row_count != null ? item.row_count : 0) +
          "</td></tr>"
        );
      })
      .join("");
    var failed = Array.isArray(report.failed_tables) ? report.failed_tables : [];
    var failedHtml = "";
    if (failed.length) {
      failedHtml =
        '<p class="pack-card-lead">Failed tables: ' +
        failed
          .map(function (item) {
            return String(item.table || "unknown");
          })
          .join(", ") +
        "</p>";
    }
    return (
      '<div class="admin-ingest-report-summary">' +
      '<div class="admin-ingest-report-stat"><strong>' +
      String(report.table_count != null ? report.table_count : tables.length) +
      '</strong><span>Tables ingested</span></div>' +
      '<div class="admin-ingest-report-stat"><strong>' +
      String(report.total_rows != null ? report.total_rows : 0) +
      '</strong><span>Total rows</span></div>' +
      "</div>" +
      failedHtml +
      '<div class="table-wrap"><table><thead><tr><th>Table</th><th>Rows</th></tr></thead><tbody>' +
      (rows || '<tr><td colspan="2">No tables found.</td></tr>') +
      "</tbody></table></div>"
    );
  }

  function openIngestReport(section, connector) {
    var reportUrl = section.getAttribute("data-pipeline-report-url");
    var dialog = document.getElementById("admin-ingest-report-dialog");
    var body = dialog ? dialog.querySelector("[data-ingest-report-body]") : null;
    if (!reportUrl || !dialog || !body) return;
    var parsed = new URL(reportUrl, window.location.href);
    parsed.searchParams.set("connector", connector);
    parsed.searchParams.set(
      "environment",
      section.getAttribute("data-pipeline-environment") || ""
    );
    parsed.searchParams.set("client_id", section.getAttribute("data-pipeline-client-id") || "");
    body.innerHTML = "<p class=\"pack-card-lead\">Loading report…</p>";
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    }
    fetch(parsed.pathname + parsed.search, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        return response.json().then(function (payload) {
          return { ok: response.ok, payload: payload };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.payload.ok) {
          throw new Error(result.payload.message || "Unable to load ingest report.");
        }
        body.innerHTML = renderIngestReportHtml(result.payload);
      })
      .catch(function (error) {
        body.innerHTML =
          "<p class=\"pack-card-lead\">" +
          (error && error.message ? error.message : "Unable to load ingest report.") +
          "</p>";
      });
  }

  function postPipelineKickoff(section, url, body, successMessage) {
    setPipelineActionStatus(section, "Starting…", true);
    return fetch(url, {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "X-HiveFlow-Inline": "1",
      },
    })
      .then(function (response) {
        return response.json().then(function (payload) {
          return { ok: response.ok, payload: payload };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.payload.ok) {
          throw new Error(result.payload.message || "Pipeline kickoff failed.");
        }
        var connector = String(result.payload.connector || "");
        var executionArn = String(result.payload.execution_arn || "");
        var rowKey = connector || "dna";
        var row = section.querySelector('[data-pipeline-row][data-pipeline-key="' + rowKey + '"]');
        if (row && executionArn) {
          var noteEl = row.querySelector("[data-pipeline-note]");
          applyPipelineRow(row, {
            status: "running",
            execution_arn: executionArn,
            has_report: false,
            note: result.payload.note || (noteEl ? noteEl.textContent : ""),
          });
        }
        setPipelineActionStatus(
          section,
          result.payload.message || successMessage,
          true
        );
        section.removeAttribute("data-pipeline-polling");
        startPipelinePolling(section);
      })
      .catch(function (error) {
        setPipelineActionStatus(
          section,
          error && error.message ? error.message : "Pipeline kickoff failed.",
          false
        );
      });
  }

  document.querySelectorAll("[data-pipeline-status-section]").forEach(function (section) {
    if (sectionHasActivePipelines(section)) {
      startPipelinePolling(section);
    }
  });

  document.addEventListener("click", function (event) {
    var ingestBtn = event.target && event.target.closest
      ? event.target.closest("[data-pipeline-ingest-kickoff]")
      : null;
    if (ingestBtn) {
      event.preventDefault();
      var ingestSection = ingestBtn.closest("[data-pipeline-status-section]");
      if (!ingestSection) return;
      var ingestUrl = ingestSection.getAttribute("data-pipeline-ingest-url");
      var connector = ingestBtn.getAttribute("data-pipeline-connector") || "";
      if (!ingestUrl || !connector) return;
      var body = new FormData();
      body.append("connector_source", connector);
      body.append(
        "environment",
        ingestSection.getAttribute("data-pipeline-environment") || ""
      );
      body.append("client_id", ingestSection.getAttribute("data-pipeline-client-id") || "");
      postPipelineKickoff(ingestSection, ingestUrl, body, "Ingest refresh started.");
      return;
    }

    var dnaBtn = event.target && event.target.closest
      ? event.target.closest("[data-pipeline-dna-kickoff]")
      : null;
    if (dnaBtn) {
      event.preventDefault();
      var dnaSection = dnaBtn.closest("[data-pipeline-status-section]");
      if (!dnaSection) return;
      var dnaUrl = dnaSection.getAttribute("data-pipeline-dna-url");
      if (!dnaUrl) return;
      var dnaBody = new FormData();
      dnaBody.append(
        "environment",
        dnaSection.getAttribute("data-pipeline-environment") || ""
      );
      dnaBody.append("client_id", dnaSection.getAttribute("data-pipeline-client-id") || "");
      postPipelineKickoff(dnaSection, dnaUrl, dnaBody, "DNA refresh started.");
      return;
    }

    var reportBtn = event.target && event.target.closest
      ? event.target.closest("[data-ingest-report-open]")
      : null;
    if (reportBtn) {
      event.preventDefault();
      var reportSection = reportBtn.closest("[data-pipeline-status-section]");
      if (!reportSection) return;
      openIngestReport(
        reportSection,
        reportBtn.getAttribute("data-ingest-report-connector") || ""
      );
      return;
    }

    var reportClose = event.target && event.target.closest
      ? event.target.closest("[data-ingest-report-close]")
      : null;
    if (!reportClose) return;
    var dialog = document.getElementById("admin-ingest-report-dialog");
    if (dialog && typeof dialog.close === "function") {
      dialog.close();
    }
  });
});
