(function () {
  "use strict";

  function formatValue(value, valueFormat) {
    if (value == null || value === "") return "—";
    var number = Number(value);
    if (Number.isNaN(number)) return String(value);

    if (valueFormat === "currency") {
      return "$" + number.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    if (valueFormat === "compact_currency") {
      if (Math.abs(number) >= 1000000) return "$" + (number / 1000000).toFixed(1) + "M";
      if (Math.abs(number) >= 1000) return "$" + Math.round(number / 1000) + "k";
      return "$" + Math.round(number).toLocaleString();
    }
    if (valueFormat === "percent") {
      return Math.abs(number) <= 1
        ? (number * 100).toFixed(1) + "%"
        : number.toFixed(1) + "%";
    }
    if (Math.abs(number) >= 1000000) return (number / 1000000).toFixed(1) + "M";
    if (Math.abs(number) >= 10000) return Math.round(number / 1000) + "k";
    if (Number.isInteger(number)) return number.toLocaleString();
    return number.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function tooltipFormatter(valueFormat) {
    return function (value) {
      if (Array.isArray(value)) {
        return formatValue(value[value.length - 1], valueFormat);
      }
      return formatValue(value, valueFormat);
    };
  }

  function applyValueFormat(option, valueFormat) {
    if (!valueFormat || !option) return option;

    var formatter = tooltipFormatter(valueFormat);
    if (option.tooltip) {
      option.tooltip.valueFormatter = formatter;
    }

    ["xAxis", "yAxis"].forEach(function (axisKey) {
      var axis = option[axisKey];
      if (!axis) return;
      var axes = Array.isArray(axis) ? axis : [axis];
      axes.forEach(function (entry) {
        if (entry && entry.type === "value") {
          entry.axisLabel = entry.axisLabel || {};
          entry.axisLabel.formatter = function (value) {
            return formatValue(value, valueFormat === "currency" ? "compact_currency" : valueFormat);
          };
        }
      });
    });

    return option;
  }

  function parseChartPayload(element) {
    var raw = element.getAttribute("data-hive-chart");
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (error) {
      console.error("HiveFlow chart: invalid payload", error);
      return null;
    }
  }

  function registerTheme() {
    if (typeof echarts === "undefined") return null;
    var themeName = window.HiveFlowEchartsThemeName || "hiveflowai";
    var theme = window.HiveFlowEchartsTheme;
    if (theme && !window.__hiveflowEchartsThemeRegistered) {
      echarts.registerTheme(themeName, theme);
      window.__hiveflowEchartsThemeRegistered = true;
    }
    return themeName;
  }

  function mountCharts() {
    if (typeof echarts === "undefined") return;

    var themeName = registerTheme();
    var mounts = document.querySelectorAll("[data-hive-chart]");
    if (!mounts.length) return;

    mounts.forEach(function (element) {
      if (element.__hiveflowChart) return;

      var payload = parseChartPayload(element);
      if (!payload || !payload.option) return;

      var option = applyValueFormat(payload.option, payload.valueFormat || "number");
      var chart = echarts.init(element, themeName, { renderer: "canvas" });
      chart.setOption(option, { notMerge: true });

      if (payload.ariaLabel) {
        element.setAttribute("aria-label", payload.ariaLabel);
      }

      element.__hiveflowChart = chart;
    });

    window.addEventListener("resize", function () {
      mounts.forEach(function (element) {
        if (element.__hiveflowChart) {
          element.__hiveflowChart.resize();
        }
      });
    });
  }

  function boot() {
    if (typeof echarts === "undefined") {
      window.addEventListener("load", boot, { once: true });
      return;
    }
    mountCharts();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
