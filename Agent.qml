import QtQuick
import Quickshell.Io

// One agent's usage record, read straight off the data file that
// omarchy-agent-usage-update maintains. The panel never learns how the
// numbers were made — a record that appears in the usage directory is an
// agent, whoever wrote it.
Item {
  id: root
  visible: false

  property string agentId: ""
  property string path: ""
  property var record: null

  readonly property int maxRecordBytes: 524288 // 512 KB limit

  FileView {
    path: root.path
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.parse(text())
    onLoadFailed: root.record = null
  }

  function parse(content) {
    if (!content || typeof content !== "string" || content.length > root.maxRecordBytes) {
      console.warn("agents", "Usage record exceeds byte limit or is invalid:", root.path)
      root.record = null
      return
    }

    try {
      var parsed = JSON.parse(content)
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        root.record = null
        return
      }

      // Producer cardinality bounds on parsed structures
      if (parsed.recentDays && Array.isArray(parsed.recentDays)) {
        if (parsed.recentDays.length > 31) parsed.recentDays = parsed.recentDays.slice(0, 31)
      }

      if (parsed.modelUsage && typeof parsed.modelUsage === "object") {
        var modelKeys = Object.keys(parsed.modelUsage)
        if (modelKeys.length > 64) {
          var limitedUsage = {}
          for (var i = 0; i < 64; i++) limitedUsage[modelKeys[i]] = parsed.modelUsage[modelKeys[i]]
          parsed.modelUsage = limitedUsage
        }
      }

      if (parsed.todayTokensByModel && typeof parsed.todayTokensByModel === "object") {
        var tokenKeys = Object.keys(parsed.todayTokensByModel)
        if (tokenKeys.length > 64) {
          var limitedTokens = {}
          for (var j = 0; j < 64; j++) limitedTokens[tokenKeys[j]] = parsed.todayTokensByModel[tokenKeys[j]]
          parsed.todayTokensByModel = limitedTokens
        }
      }

      if (parsed.limits && Array.isArray(parsed.limits)) {
        if (parsed.limits.length > 64) parsed.limits = parsed.limits.slice(0, 64)
      }

      root.record = parsed
    } catch (e) {
      console.warn("agents", "Ignoring bad usage record", root.path, e)
      root.record = null
    }
  }
}
