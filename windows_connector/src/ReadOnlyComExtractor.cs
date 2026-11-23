using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;

namespace Vortexen.PlanSwiftConnector
{
    public sealed class ComExtractedProperty
    {
        public string property_guid { get; set; }
        public string formula { get; set; }
        public string result { get; set; }
        public string property_class { get; set; }
        public string units { get; set; }
        public string group { get; set; }
        public string expression { get; set; }
    }

    public sealed class ComExtractedPoint
    {
        public int point_order { get; set; }
        public double x { get; set; }
        public double y { get; set; }
        public string point_type { get; set; }
    }

    public sealed class ComExtractedObject
    {
        public string native_guid { get; set; }
        public string native_class { get; set; }
        public string native_type { get; set; }
        public string name { get; set; }
        public string full_path { get; set; }
        public string parent_guid { get; set; }
        public int depth { get; set; }
        public List<string> child_guids { get; set; }
        public List<ComExtractedPoint> points { get; set; }
        public Dictionary<string, ComExtractedProperty> properties { get; set; }
    }

    public sealed class ComExtractionSnapshot
    {
        public string source_system { get; set; }
        public string connector_version { get; set; }
        public string extraction_scope { get; set; }
        public string planswift_version { get; set; }
        public string edition { get; set; }
        public string prog_id { get; set; }
        public string extracted_at_utc { get; set; }
        public bool read_only { get; set; }
        public Dictionary<string, string> project { get; set; }
        public List<ComExtractedObject> objects { get; set; }
        public List<string> warnings { get; set; }
    }

    public sealed class ComExtractionOptions
    {
        public ComExtractionOptions()
        {
            FastMode = true;
            PagesOnly = false;
            IncludePoints = false;
            AllowRootFallback = false;
            ConnectTimeoutSeconds = 20;
            SkipPageDimensions = false;
            MaxSeconds = 300;
            MaxItems = 100000;
            ProgressWriter = Console.Out;
        }

        public bool FastMode { get; set; }
        public bool PagesOnly { get; set; }
        public bool IncludePoints { get; set; }
        public bool AllowRootFallback { get; set; }
        public string ExpectedJobGuid { get; set; }
        public int ConnectTimeoutSeconds { get; set; }
        public bool SkipPageDimensions { get; set; }
        public int MaxSeconds { get; set; }
        public int MaxItems { get; set; }
        public Func<bool> IsCancelled { get; set; }
        public TextWriter ProgressWriter { get; set; }
    }

    /// <summary>
    /// Strictly read-only late-bound IDispatch COM extractor verified against PlanSwift 11 TypeLib
    /// ({60A9C20E-DE24-420D-B22E-C43286CC9AA6}: IPlanSwift, IItem, IPropertyObject, IPoint) and PlanSwift 12+.
    /// Hard-skips binary/image properties (e.g., Icon) whose ResultAsString() stalls ~1.5s/item.
    /// Never invokes SetPropertyFormula, Delete, NewItem, NewPoint, or any mutating method.
    /// </summary>
    public sealed class ReadOnlyComExtractor
    {
        private static readonly HashSet<string> BinaryPropertyBlacklist = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "Icon", "Image", "Thumb", "Thumbnail", "Bitmap", "ImageData",
            "DigitizerData", "PageImage", "Preview", "Picture", "Glyph",
            "ImageFile", "Photo", "Snapshot"
        };

        private static readonly HashSet<string> ComputedPropertyNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "Qty", "PageWidth", "PageHeight", "Scale", "ScaleUnits", "ScaleX", "ScaleY",
            "DPI", "Area", "Length", "Linear", "Volume", "Depth", "Width", "Height",
            "Count", "Takeoff", "Price", "Total", "Cost", "UnitCost", "Page", "sep",
            "Line Width"
        };

        private readonly string _progId;
        private readonly ComExtractionOptions _options;

        public ReadOnlyComExtractor(string progId, ComExtractionOptions options = null)
        {
            _progId = progId;
            _options = options ?? new ComExtractionOptions();
        }

        public ReadOnlyComExtractor(string progId, int maxItems)
            : this(progId, new ComExtractionOptions { MaxItems = maxItems })
        {
        }

        public ComExtractionSnapshot ExtractCurrentJob()
        {
            var comType = Type.GetTypeFromProgID(_progId, false);
            if (comType == null)
            {
                throw new InvalidOperationException(
                    string.Format("PlanSwift COM ProgID '{0}' is not registered on this machine.", _progId));
            }

            EnsurePlanSwiftWindowReady();

            object app = null;
            System.Threading.Timer connectWatchdog = null;
            System.Threading.Timer overallWatchdog = null;
            try
            {
                if (_options.ConnectTimeoutSeconds > 0)
                {
                    int connectTimeoutSec = _options.ConnectTimeoutSeconds;
                    connectWatchdog = new System.Threading.Timer(_ =>
                    {
                        Console.Error.WriteLine(CanonicalPayloadBuilder.SerializeJson(new
                        {
                            error = "ComConnectionTimeout",
                            message = string.Format(
                                "PlanSwift COM did not respond within {0}s. Check if PlanSwift has an open modal/popup dialog or restart PlanSwift.",
                                connectTimeoutSec)
                        }));
                        Console.Error.Flush();
                        Environment.Exit(4);
                    }, null, connectTimeoutSec * 1000, Timeout.Infinite);
                }

                try
                {
                    app = Marshal.GetActiveObject(_progId);
                }
                catch
                {
                    app = Activator.CreateInstance(comType);
                }

                if (app == null)
                {
                    throw new InvalidOperationException("Unable to instantiate PlanSwift COM server.");
                }

                var warnings = new List<string>();
                string versionStr = SafeInvokeString(app, "CurrentVersion", null) ?? SafeGetStringProperty(app, "Version", "unknown");
                string editionStr = SafeInvokeString(app, "Edition", null) ?? "";
                bool? isJobOpen = SafeInvokeBool(app, "IsJobOpen", null);

                LogProgress("Connected to {0} (Version: {1}, Edition: {2}, IsJobOpen: {3})",
                    _progId,
                    string.IsNullOrWhiteSpace(versionStr) ? "unknown" : versionStr,
                    string.IsNullOrWhiteSpace(editionStr) ? "standard" : editionStr,
                    isJobOpen.HasValue ? isJobOpen.Value.ToString() : "unknown");

                object rootItem = SafeInvokeSilent(app, "GetItem", new object[] { "\\Job" });
                if (rootItem == null)
                {
                    if (_options.AllowRootFallback)
                    {
                        warnings.Add("GetItem('\\Job') returned null; falling back to Root() because --allow-root was specified.");
                        rootItem = SafeInvoke(app, "Root", null, warnings);
                    }
                    else
                    {
                        throw new InvalidOperationException(
                            "PlanSwift GetItem('\\Job') returned null. Open a job in PlanSwift Desktop and retry (or pass --allow-root to inspect Root).");
                    }
                }

                if (rootItem == null)
                {
                    throw new InvalidOperationException(
                        "PlanSwift returned null for the job root item. Ensure PlanSwift Desktop has an open job.");
                }

                if (connectWatchdog != null)
                {
                    connectWatchdog.Dispose();
                    connectWatchdog = null;
                }

                if (_options.MaxSeconds > 0)
                {
                    int overallLimitSec = _options.MaxSeconds + 15;
                    overallWatchdog = new System.Threading.Timer(_ =>
                    {
                        Console.Error.WriteLine(CanonicalPayloadBuilder.SerializeJson(new
                        {
                            error = "ComTraversalTimeout",
                            message = string.Format("PlanSwift COM call hung past hard limit ({0}s).", overallLimitSec)
                        }));
                        Console.Error.Flush();
                        Environment.Exit(4);
                    }, null, overallLimitSec * 1000, Timeout.Infinite);
                }

                var objects = new List<ComExtractedObject>();
                var visited = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                var stopwatch = Stopwatch.StartNew();
                int formulasEvaluated = 0;
                bool stoppedEarly = false;

                try
                {
                    string itemGuid = SafeInvokeString(rootItem, "GUID", null) ?? "";
                    string propGuid = SafeInvokeString(rootItem, "GetPropertyResultAsString", new object[] { "GUID", "" }) ?? "";
                    string itemName = SafeGetStringProperty(rootItem, "Name", "");
                    string propName = SafeInvokeString(rootItem, "GetPropertyResultAsString", new object[] { "Name", "" }) ?? "";

                    string effectiveJobGuid = !string.IsNullOrWhiteSpace(propGuid) ? propGuid : itemGuid;
                    string effectiveJobName = (!string.IsNullOrWhiteSpace(propName) && !string.Equals(propName, "Job", StringComparison.OrdinalIgnoreCase))
                        ? propName
                        : itemName;

                    var candidateGuids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    if (!string.IsNullOrWhiteSpace(itemGuid)) candidateGuids.Add(NormalizeGuid(itemGuid));
                    if (!string.IsNullOrWhiteSpace(propGuid)) candidateGuids.Add(NormalizeGuid(propGuid));

                    var folderGuidParts = InspectTopLevelJobSummary(rootItem, effectiveJobName, effectiveJobGuid, candidateGuids, warnings);

                    if (!string.IsNullOrWhiteSpace(_options.ExpectedJobGuid))
                    {
                        bool matchedExpected = false;
                        string[] expectedParts = _options.ExpectedJobGuid.Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
                        foreach (string rawPart in expectedParts)
                        {
                            string expectedNorm = NormalizeGuid(rawPart);
                            if (!string.IsNullOrWhiteSpace(expectedNorm) && candidateGuids.Contains(expectedNorm))
                            {
                                matchedExpected = true;
                                break;
                            }
                        }

                        if (!matchedExpected)
                        {
                            throw new InvalidOperationException(string.Format(
                                "Active PlanSwift job mismatch: active job '{0}' has root GUIDs [effective={1}, mount={2}] and folder GUIDs [{3}]; expected one of [{4}]. Open the matching native .SwiftJob file in PlanSwift and retry.",
                                effectiveJobName,
                                string.IsNullOrWhiteSpace(effectiveJobGuid) ? "none" : effectiveJobGuid,
                                string.IsNullOrWhiteSpace(itemGuid) ? "none" : itemGuid,
                                folderGuidParts.Count > 0 ? string.Join(", ", folderGuidParts) : "none",
                                _options.ExpectedJobGuid));
                        }
                    }

                    if (_options.PagesOnly)
                    {
                        LogProgress("Starting --pages-only PageWidth/PageHeight COM extraction (MaxSeconds={0}s)...",
                            _options.MaxSeconds);
                        ExtractPagesDimensionsOnly(
                            app,
                            rootItem,
                            effectiveJobGuid,
                            objects,
                            visited,
                            warnings,
                            stopwatch,
                            ref formulasEvaluated,
                            ref stoppedEarly);
                    }
                    else
                    {
                        LogProgress("Starting {0} COM traversal (IncludePoints={1}, SkipPageDimensions={2}, MaxSeconds={3}s)...",
                            _options.FastMode ? "fast" : "full",
                            _options.IncludePoints,
                            _options.SkipPageDimensions,
                            _options.MaxSeconds);

                        TraverseItem(
                            rootItem,
                            null,
                            0,
                            objects,
                            visited,
                            warnings,
                            stopwatch,
                            ref formulasEvaluated,
                            ref stoppedEarly,
                            effectiveJobGuid,
                            effectiveJobName);
                    }
                }
                finally
                {
                    SafeRelease(rootItem);
                }

                stopwatch.Stop();
                LogProgress("Completed COM extraction: {0} objects, {1} evaluated formulas in {2:0.00}s",
                    objects.Count, formulasEvaluated, stopwatch.Elapsed.TotalSeconds);

                var rootMeta = new Dictionary<string, string>();
                if (objects.Count > 0)
                {
                    rootMeta["native_guid"] = objects[0].native_guid;
                    rootMeta["name"] = objects[0].name;
                }

                return new ComExtractionSnapshot
                {
                    source_system = "PlanSwiftCOM",
                    connector_version = "1.2.4",
                    extraction_scope = _options.PagesOnly ? "pages_only" : "full_job",
                    planswift_version = string.IsNullOrWhiteSpace(versionStr) ? "unknown" : versionStr,
                    edition = editionStr,
                    prog_id = _progId,
                    extracted_at_utc = DateTime.UtcNow.ToString("o"),
                    read_only = true,
                    project = rootMeta,
                    objects = objects,
                    warnings = warnings
                };
            }
            finally
            {
                if (connectWatchdog != null)
                {
                    connectWatchdog.Dispose();
                    connectWatchdog = null;
                }
                if (overallWatchdog != null)
                {
                    overallWatchdog.Dispose();
                    overallWatchdog = null;
                }
                SafeRelease(app);
            }
        }

        private void EnsurePlanSwiftWindowReady()
        {
            Process[] procs = Process.GetProcessesByName("PlanSwift");
            try
            {
                if (procs.Length == 0)
                {
                    throw new InvalidOperationException(
                        "PlanSwift Desktop is not running. Launch PlanSwift Desktop, open your .SwiftJob project, and retry.");
                }

                bool anyVisibleWindow = false;
                var pidList = new List<string>();
                foreach (var p in procs)
                {
                    try
                    {
                        pidList.Add(p.Id.ToString());
                        p.Refresh();
                        if (p.MainWindowHandle != IntPtr.Zero)
                        {
                            anyVisibleWindow = true;
                        }
                    }
                    catch
                    {
                        // Ignore transiently exiting process handle inspection errors
                    }
                }

                if (!anyVisibleWindow)
                {
                    LogProgress("[INFO] PlanSwift.exe (PID {0}) has no top-level MainWindowHandle (may be minimized/Delphi VCL); proceeding with connect watchdog...",
                        string.Join(", ", pidList));
                }
            }
            finally
            {
                foreach (var p in procs)
                {
                    try { p.Dispose(); } catch { }
                }
            }
        }

        private List<string> InspectTopLevelJobSummary(
            object rootItem,
            string jobName,
            string jobGuid,
            HashSet<string> candidateGuids,
            List<string> warnings)
        {
            if (SafeInvokeBool(rootItem, "HasChildren", null) == true)
            {
                SafeInvokeSilent(rootItem, "LoadChildren", null);
            }

            int topCount = SafeInvokeInt(rootItem, "ChildCount", null, -1);
            if (topCount < 0) topCount = SafeGetIntProperty(rootItem, "ChildCount", 0);

            var folderParts = new List<string>();
            var folderGuidParts = new List<string>();
            int takeoffChildCount = -1;

            for (int i = 0; i < topCount; i++)
            {
                object child = SafeGetIndexedProperty(rootItem, "ChildItem", i);
                if (child == null) continue;
                try
                {
                    string cName = SafeGetStringProperty(child, "Name", "");
                    string cGuid = SafeInvokeString(child, "GUID", null) ?? "";
                    string cPropGuid = SafeInvokeString(child, "GetPropertyResultAsString", new object[] { "GUID", "" }) ?? "";
                    if (!string.IsNullOrWhiteSpace(cGuid)) candidateGuids.Add(NormalizeGuid(cGuid));
                    if (!string.IsNullOrWhiteSpace(cPropGuid)) candidateGuids.Add(NormalizeGuid(cPropGuid));
                    string displayGuid = !string.IsNullOrWhiteSpace(cPropGuid) ? cPropGuid : cGuid;

                    int subCount = SafeInvokeInt(child, "ChildCount", null, -1);
                    if (subCount < 0) subCount = SafeGetIntProperty(child, "ChildCount", 0);
                    folderParts.Add(string.Format("{0} ({1})", cName, subCount));
                    folderGuidParts.Add(string.Format("{0}={1}", cName, displayGuid));
                    if (string.Equals(cName, "Takeoff", StringComparison.OrdinalIgnoreCase))
                    {
                        takeoffChildCount = subCount;
                    }
                }
                finally
                {
                    SafeRelease(child);
                }
            }

            LogProgress("Active Job: '{0}' | GUID: {1} | Folders: {2}",
                string.IsNullOrWhiteSpace(jobName) ? "(unnamed)" : jobName,
                string.IsNullOrWhiteSpace(jobGuid) ? "(none)" : jobGuid,
                folderParts.Count > 0 ? string.Join(", ", folderParts) : "none");

            if (takeoffChildCount == 0)
            {
                string warn = "Active PlanSwift job has 0 children under Takeoff folder (if you imported a .SwiftJob.zip directly, copy it as a .SwiftJob file so PlanSwift restores takeoffs and original GUIDs).";
                warnings.Add(warn);
                LogProgress("[WARNING] {0}", warn);
            }

            return folderGuidParts;
        }

        private void ExtractPagesDimensionsOnly(
            object app,
            object rootItem,
            string rootGuid,
            List<ComExtractedObject> output,
            HashSet<string> visited,
            List<string> warnings,
            Stopwatch stopwatch,
            ref int formulasEvaluated,
            ref bool stoppedEarly)
        {
            object pagesRoot = SafeInvokeSilent(app, "GetItem", new object[] { "\\Job\\Pages" });
            if (pagesRoot == null)
            {
                int topCount = SafeInvokeInt(rootItem, "ChildCount", null, -1);
                if (topCount < 0) topCount = SafeGetIntProperty(rootItem, "ChildCount", 0);
                for (int i = 0; i < topCount; i++)
                {
                    object child = SafeGetIndexedProperty(rootItem, "ChildItem", i);
                    if (child == null) continue;
                    string cName = SafeGetStringProperty(child, "Name", "");
                    if (string.Equals(cName, "Pages", StringComparison.OrdinalIgnoreCase))
                    {
                        pagesRoot = child;
                        break;
                    }
                    SafeRelease(child);
                }
            }

            if (pagesRoot == null)
            {
                warnings.Add("Pages folder not found under \\Job; --pages-only extracted 0 pages.");
                return;
            }

            try
            {
                int pagesCount = 0;
                int consecutiveErrors = 0;
                CollectPagesDimensionsRecursive(
                    pagesRoot,
                    rootGuid,
                    1,
                    output,
                    visited,
                    warnings,
                    stopwatch,
                    ref formulasEvaluated,
                    ref pagesCount,
                    ref consecutiveErrors,
                    ref stoppedEarly);
            }
            finally
            {
                SafeRelease(pagesRoot);
            }
        }

        private void CollectPagesDimensionsRecursive(
            object item,
            string parentGuid,
            int depth,
            List<ComExtractedObject> output,
            HashSet<string> visited,
            List<string> warnings,
            Stopwatch stopwatch,
            ref int formulasEvaluated,
            ref int pagesCount,
            ref int consecutiveErrors,
            ref bool stoppedEarly)
        {
            if (stoppedEarly) return;
            if (_options.IsCancelled != null && _options.IsCancelled())
            {
                stoppedEarly = true;
                warnings.Add("COM --pages-only extraction stopped early due to user cancellation.");
                return;
            }
            if (_options.MaxSeconds > 0 && stopwatch.Elapsed.TotalSeconds >= _options.MaxSeconds)
            {
                stoppedEarly = true;
                warnings.Add(string.Format("COM --pages-only reached --max-seconds ({0}s) at {1} pages.", _options.MaxSeconds, pagesCount));
                return;
            }
            if (output.Count >= _options.MaxItems)
            {
                stoppedEarly = true;
                warnings.Add("Reached configured safety maxItems cap during --pages-only traversal.");
                return;
            }

            string itemType = SafeGetStringProperty(item, "ItemType", "");
            if (string.IsNullOrWhiteSpace(itemType))
            {
                itemType = SafeInvokeString(item, "GetPropertyResultAsString", new object[] { "Type", "" }) ?? "";
            }
            string itemClass = SafeInvokeString(item, "GetClassName", null) ?? SafeGetStringProperty(item, "ClassName", itemType);
            string name = SafeGetStringProperty(item, "Name", "");
            if (string.IsNullOrWhiteSpace(name))
            {
                name = SafeInvokeString(item, "GetPropertyResultAsString", new object[] { "Name", "" }) ?? "";
            }

            bool isPage = string.Equals(itemClass, "Page", StringComparison.OrdinalIgnoreCase)
                || string.Equals(itemType, ".TIFF Page", StringComparison.OrdinalIgnoreCase)
                || (itemType != null && itemType.IndexOf("Page", StringComparison.OrdinalIgnoreCase) >= 0);

            if (isPage)
            {
                string guid = SafeInvokeString(item, "GUID", null);
                if (string.IsNullOrWhiteSpace(guid))
                {
                    guid = SafeInvokeString(item, "GetPropertyResultAsString", new object[] { "GUID", "" }) ?? "";
                }
                if (string.IsNullOrWhiteSpace(guid))
                {
                    guid = string.Format("COM-PAGE-UNKEYED-{0}", output.Count + 1);
                }
                if (!visited.Add(guid))
                {
                    return;
                }

                string fullPath = SafeInvokeString(item, "FullPath", null) ?? "";
                string wFormula = SafeInvokeString(item, "GetPropertyFormula", new object[] { "PageWidth" });
                string hFormula = SafeInvokeString(item, "GetPropertyFormula", new object[] { "PageHeight" });
                bool hasDimFormula = !string.IsNullOrWhiteSpace(wFormula) || !string.IsNullOrWhiteSpace(hFormula);

                string wRes = !string.IsNullOrWhiteSpace(wFormula)
                    ? SafeInvokeString(item, "GetPropertyResultAsString", new object[] { "PageWidth", "" })
                    : null;
                string hRes = !string.IsNullOrWhiteSpace(hFormula)
                    ? SafeInvokeString(item, "GetPropertyResultAsString", new object[] { "PageHeight", "" })
                    : null;

                var props = new Dictionary<string, ComExtractedProperty>(StringComparer.Ordinal);
                bool wOk = IsValidDimensionResult(wRes);
                bool hOk = IsValidDimensionResult(hRes);

                if (wOk)
                {
                    props["PageWidth"] = new ComExtractedProperty
                    {
                        formula = wFormula,
                        result = wRes.Trim(),
                        property_class = "COM"
                    };
                    formulasEvaluated++;
                }
                if (hOk)
                {
                    props["PageHeight"] = new ComExtractedProperty
                    {
                        formula = hFormula,
                        result = hRes.Trim(),
                        property_class = "COM"
                    };
                    formulasEvaluated++;
                }

                if (hasDimFormula)
                {
                    if (wOk || hOk)
                    {
                        consecutiveErrors = 0;
                    }
                    else
                    {
                        consecutiveErrors++;
                    }
                }

                if (props.Count > 0)
                {
                    output.Add(new ComExtractedObject
                    {
                        native_guid = guid,
                        native_class = string.IsNullOrWhiteSpace(itemClass) ? "Page" : itemClass,
                        native_type = itemType,
                        name = name,
                        full_path = fullPath,
                        parent_guid = parentGuid,
                        depth = depth,
                        child_guids = new List<string>(),
                        points = new List<ComExtractedPoint>(),
                        properties = props
                    });
                }

                pagesCount++;
                if (pagesCount % 10 == 0)
                {
                    LogProgress("[{0} pages | {1:0.0}s | {2} evaluated] {3} => {4} x {5}",
                        pagesCount,
                        stopwatch.Elapsed.TotalSeconds,
                        formulasEvaluated,
                        name,
                        wOk ? wRes.Trim() : "?",
                        hOk ? hRes.Trim() : "?");
                }

                if (consecutiveErrors >= 10)
                {
                    stoppedEarly = true;
                    string warn = string.Format(
                        "Stopping --pages-only early after 10 consecutive empty/error page evaluations (possible 32-bit PlanSwift TIFF memory limit); preserving {0} evaluated pages.",
                        output.Count);
                    warnings.Add(warn);
                    LogProgress("[WARNING] {0}", warn);
                }
                return;
            }

            if (SafeInvokeBool(item, "HasChildren", null) == true)
            {
                SafeInvokeSilent(item, "LoadChildren", null);
            }

            int childCount = SafeInvokeInt(item, "ChildCount", null, -1);
            if (childCount < 0)
            {
                childCount = SafeGetIntProperty(item, "ChildCount", 0);
            }

            string folderGuid = SafeInvokeString(item, "GUID", null) ?? parentGuid;
            for (int i = 0; i < childCount; i++)
            {
                if (stoppedEarly) break;
                object child = SafeGetIndexedProperty(item, "ChildItem", i);
                if (child == null)
                {
                    child = SafeInvoke(item, "ChildItem", new object[] { i }, warnings);
                }
                if (child == null) continue;
                try
                {
                    CollectPagesDimensionsRecursive(
                        child,
                        folderGuid,
                        depth + 1,
                        output,
                        visited,
                        warnings,
                        stopwatch,
                        ref formulasEvaluated,
                        ref pagesCount,
                        ref consecutiveErrors,
                        ref stoppedEarly);
                }
                finally
                {
                    SafeRelease(child);
                }
            }
        }

        private static bool IsValidDimensionResult(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return false;
            string trimmed = value.Trim();
            if (trimmed.StartsWith("error", StringComparison.OrdinalIgnoreCase)) return false;
            return true;
        }

        private string TraverseItem(
            object item,
            string parentGuid,
            int depth,
            List<ComExtractedObject> output,
            HashSet<string> visited,
            List<string> warnings,
            Stopwatch stopwatch,
            ref int formulasEvaluated,
            ref bool stoppedEarly,
            string rootGuidOverride = null,
            string rootNameOverride = null)
        {
            if (stoppedEarly)
            {
                return null;
            }
            if (_options.IsCancelled != null && _options.IsCancelled())
            {
                stoppedEarly = true;
                warnings.Add("COM extraction stopped early due to user cancellation.");
                LogProgress("[STOPPED] Cancellation requested at {0} objects ({1:0.0}s).", output.Count, stopwatch.Elapsed.TotalSeconds);
                return null;
            }
            if (_options.MaxSeconds > 0 && stopwatch.Elapsed.TotalSeconds >= _options.MaxSeconds)
            {
                stoppedEarly = true;
                string warn = string.Format("COM extraction reached --max-seconds limit ({0}s) at {1} objects.", _options.MaxSeconds, output.Count);
                warnings.Add(warn);
                LogProgress("[STOPPED] {0}", warn);
                return null;
            }
            if (output.Count >= _options.MaxItems)
            {
                stoppedEarly = true;
                warnings.Add("Reached configured safety maxItems cap during COM traversal.");
                return null;
            }

            string guid = (depth == 0 && !string.IsNullOrWhiteSpace(rootGuidOverride))
                ? rootGuidOverride
                : SafeInvokeString(item, "GUID", null);
            if (string.IsNullOrWhiteSpace(guid))
            {
                guid = SafeInvokeString(item, "GetPropertyResultAsString", new object[] { "GUID", "" }) ?? "";
            }
            string name = (depth == 0 && !string.IsNullOrWhiteSpace(rootNameOverride))
                ? rootNameOverride
                : SafeGetStringProperty(item, "Name", "");
            if (string.IsNullOrWhiteSpace(name))
            {
                name = SafeInvokeString(item, "GetPropertyResultAsString", new object[] { "Name", "" }) ?? "";
            }
            string itemType = SafeGetStringProperty(item, "ItemType", "");
            if (string.IsNullOrWhiteSpace(itemType))
            {
                itemType = SafeInvokeString(item, "GetPropertyResultAsString", new object[] { "Type", "" }) ?? "";
            }
            string itemClass = SafeInvokeString(item, "GetClassName", null) ?? SafeGetStringProperty(item, "ClassName", itemType);
            string fullPath = SafeInvokeString(item, "FullPath", null) ?? "";

            if (string.IsNullOrWhiteSpace(guid))
            {
                guid = string.Format("COM-UNKEYED-{0}", output.Count + 1);
                warnings.Add(string.Format("Object '{0}' lacked GUID via COM.", name));
            }
            if (!visited.Add(guid))
            {
                return guid;
            }

            var props = ReadItemProperties(item, _options.FastMode, _options.SkipPageDimensions, ref formulasEvaluated);
            var points = _options.IncludePoints ? ReadItemPoints(item) : new List<ComExtractedPoint>();
            var childGuids = new List<string>();

            // Only invoke LoadChildren() when HasChildren() reports true (avoid unnecessary lazy-load RPC on leaf items)
            if (SafeInvokeBool(item, "HasChildren", null) == true)
            {
                SafeInvokeSilent(item, "LoadChildren", null);
            }

            int childCount = SafeInvokeInt(item, "ChildCount", null, -1);
            if (childCount < 0)
            {
                childCount = SafeGetIntProperty(item, "ChildCount", 0);
            }

            var extracted = new ComExtractedObject
            {
                native_guid = guid,
                native_class = string.IsNullOrWhiteSpace(itemClass) ? "Item" : itemClass,
                native_type = itemType,
                name = name,
                full_path = fullPath,
                parent_guid = parentGuid,
                depth = depth,
                child_guids = childGuids,
                points = points,
                properties = props
            };
            output.Add(extracted);

            if (output.Count % 25 == 0)
            {
                LogProgress("[{0} objs | {1:0.0}s | {2} formulas] {3}: {4}",
                    output.Count,
                    stopwatch.Elapsed.TotalSeconds,
                    formulasEvaluated,
                    string.IsNullOrWhiteSpace(itemType) ? extracted.native_class : itemType,
                    name);
            }

            for (int i = 0; i < childCount; i++)
            {
                if (stoppedEarly) break;

                object child = SafeGetIndexedProperty(item, "ChildItem", i);
                if (child == null)
                {
                    child = SafeInvoke(item, "ChildItem", new object[] { i }, warnings);
                }
                if (child == null) continue;
                try
                {
                    string childGuid = TraverseItem(
                        child,
                        guid,
                        depth + 1,
                        output,
                        visited,
                        warnings,
                        stopwatch,
                        ref formulasEvaluated,
                        ref stoppedEarly);
                    if (!string.IsNullOrWhiteSpace(childGuid))
                    {
                        childGuids.Add(childGuid);
                    }
                }
                finally
                {
                    SafeRelease(child);
                }
            }

            return guid;
        }

        private static Dictionary<string, ComExtractedProperty> ReadItemProperties(
            object item,
            bool fastMode,
            bool skipPageDimensions,
            ref int formulasEvaluated)
        {
            var dict = new Dictionary<string, ComExtractedProperty>(StringComparer.Ordinal);
            int propCount = SafeInvokeInt(item, "PropertyCount", null, -1);
            if (propCount < 0)
            {
                propCount = SafeGetIntProperty(item, "PropertyCount", 0);
            }

            for (int i = 0; i < propCount; i++)
            {
                // PlanSwift 11 verified IItem.PropertyItem(Index) -> IPropertyObject
                object propObj = SafeGetIndexedProperty(item, "PropertyItem", i);
                if (propObj != null)
                {
                    try
                    {
                        string pName = SafeGetStringProperty(propObj, "Name", "");
                        if (string.IsNullOrEmpty(pName) || BinaryPropertyBlacklist.Contains(pName))
                        {
                            continue;
                        }
                        bool isPageDim = skipPageDimensions && IsPageDimensionProperty(pName);
                        if (fastMode && isPageDim)
                        {
                            continue;
                        }

                        string formula = SafeGetStringProperty(propObj, "Formula", null);
                        if (fastMode)
                        {
                            bool needsEval = IsFormulaOrComputed(pName, formula);
                            if (!needsEval)
                            {
                                continue;
                            }

                            string result = SafeInvokeString(propObj, "ResultAsString", null);
                            formulasEvaluated++;
                            if (!dict.ContainsKey(pName))
                            {
                                dict[pName] = new ComExtractedProperty
                                {
                                    formula = formula,
                                    result = result,
                                    property_class = "COM"
                                };
                            }
                        }
                        else
                        {
                            string pGuid = SafeInvokeString(propObj, "GUID", null) ?? "";
                            string result = isPageDim ? null : SafeInvokeString(propObj, "ResultAsString", null);
                            string units = SafeGetStringProperty(propObj, "Units", "");
                            string group = SafeGetStringProperty(propObj, "Group", "");
                            string pClass = SafeInvokeString(propObj, "PropertyType", null) ?? "COM";
                            string expr = SafeGetStringProperty(propObj, "Expression", "");
                            if (!isPageDim)
                            {
                                formulasEvaluated++;
                            }

                            if (!dict.ContainsKey(pName))
                            {
                                dict[pName] = new ComExtractedProperty
                                {
                                    property_guid = pGuid,
                                    formula = formula,
                                    result = result,
                                    property_class = pClass,
                                    units = units,
                                    group = group,
                                    expression = expr
                                };
                            }
                        }
                    }
                    finally
                    {
                        SafeRelease(propObj);
                    }
                }
                else
                {
                    // Fallback for PlanSwift builds exposing PropertyName(i)
                    string pName = SafeInvokeString(item, "PropertyName", new object[] { i });
                    if (string.IsNullOrEmpty(pName) || BinaryPropertyBlacklist.Contains(pName)) continue;
                    bool isPageDim = skipPageDimensions && IsPageDimensionProperty(pName);
                    if (fastMode && isPageDim)
                    {
                        continue;
                    }

                    string formula = SafeInvokeString(item, "GetPropertyFormula", new object[] { pName });
                    if (fastMode && !IsFormulaOrComputed(pName, formula))
                    {
                        continue;
                    }

                    string result = isPageDim
                        ? null
                        : (SafeInvokeString(item, "GetPropertyResultAsString", new object[] { pName, "" })
                            ?? SafeInvokeString(item, "GetPropertyResult", new object[] { pName }));
                    if (!isPageDim)
                    {
                        formulasEvaluated++;
                    }
                    if (!dict.ContainsKey(pName))
                    {
                        dict[pName] = new ComExtractedProperty
                        {
                            formula = formula,
                            result = result,
                            property_class = "COM"
                        };
                    }
                }
            }
            return dict;
        }

        private static bool IsPageDimensionProperty(string propName)
        {
            return string.Equals(propName, "PageWidth", StringComparison.OrdinalIgnoreCase)
                || string.Equals(propName, "PageHeight", StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsFormulaOrComputed(string propName, string formula)
        {
            if (ComputedPropertyNames.Contains(propName))
            {
                return true;
            }
            if (!string.IsNullOrEmpty(formula))
            {
                if (formula.IndexOf('[') >= 0 ||
                    formula.IndexOf(":=", StringComparison.Ordinal) >= 0 ||
                    formula.IndexOf('\n') >= 0)
                {
                    return true;
                }
            }
            return false;
        }

        private static string NormalizeGuid(string raw)
        {
            return (raw ?? "").Trim().Trim('{', '}').ToUpperInvariant();
        }

        private void LogProgress(string format, params object[] args)
        {
            if (_options.ProgressWriter == null) return;
            try
            {
                _options.ProgressWriter.WriteLine(string.Format(format, args));
                _options.ProgressWriter.Flush();
            }
            catch
            {
                // Best-effort console progress logging
            }
        }

        private static List<ComExtractedPoint> ReadItemPoints(object item)
        {
            var pts = new List<ComExtractedPoint>();
            int ptCount = SafeInvokeInt(item, "PointCount", null, 0);
            for (int i = 0; i < ptCount; i++)
            {
                object ptObj = SafeInvokeSilent(item, "GetPoint", new object[] { i });
                if (ptObj == null) continue;
                try
                {
                    double x = SafeGetDoubleProperty(ptObj, "X", 0.0);
                    double y = SafeGetDoubleProperty(ptObj, "Y", 0.0);
                    string pType = SafeGetStringProperty(ptObj, "PointType", "Normal");
                    pts.Add(new ComExtractedPoint
                    {
                        point_order = i,
                        x = x,
                        y = y,
                        point_type = pType
                    });
                }
                finally
                {
                    SafeRelease(ptObj);
                }
            }
            return pts;
        }

        private static object SafeInvoke(object target, string method, object[] args, List<string> warnings)
        {
            try
            {
                return target.GetType().InvokeMember(method, BindingFlags.InvokeMethod | BindingFlags.GetProperty, null, target, args);
            }
            catch (Exception ex)
            {
                warnings.Add(string.Format("COM call '{0}' unavailable or failed: {1}", method, ex.Message));
                return null;
            }
        }

        private static object SafeInvokeSilent(object target, string method, object[] args)
        {
            try
            {
                return target.GetType().InvokeMember(method, BindingFlags.InvokeMethod | BindingFlags.GetProperty, null, target, args);
            }
            catch
            {
                return null;
            }
        }

        private static object SafeGetIndexedProperty(object target, string propName, int index)
        {
            try
            {
                return target.GetType().InvokeMember(propName, BindingFlags.GetProperty | BindingFlags.InvokeMethod, null, target, new object[] { index });
            }
            catch
            {
                return null;
            }
        }

        private static string SafeInvokeString(object target, string method, object[] args)
        {
            try
            {
                object val = target.GetType().InvokeMember(method, BindingFlags.InvokeMethod | BindingFlags.GetProperty, null, target, args);
                return val != null ? Convert.ToString(val) : null;
            }
            catch
            {
                return null;
            }
        }

        private static bool? SafeInvokeBool(object target, string method, object[] args)
        {
            try
            {
                object val = target.GetType().InvokeMember(method, BindingFlags.InvokeMethod | BindingFlags.GetProperty, null, target, args);
                return val != null ? (bool?)Convert.ToBoolean(val) : null;
            }
            catch
            {
                return null;
            }
        }

        private static int SafeInvokeInt(object target, string method, object[] args, int fallback)
        {
            try
            {
                object val = target.GetType().InvokeMember(method, BindingFlags.InvokeMethod | BindingFlags.GetProperty, null, target, args);
                return val != null ? Convert.ToInt32(val) : fallback;
            }
            catch
            {
                return fallback;
            }
        }

        private static string SafeGetStringProperty(object target, string prop, string fallback)
        {
            try
            {
                object val = target.GetType().InvokeMember(prop, BindingFlags.GetProperty, null, target, null);
                return val != null ? Convert.ToString(val) : fallback;
            }
            catch
            {
                return fallback;
            }
        }

        private static int SafeGetIntProperty(object target, string prop, int fallback)
        {
            try
            {
                object val = target.GetType().InvokeMember(prop, BindingFlags.GetProperty, null, target, null);
                return val != null ? Convert.ToInt32(val) : fallback;
            }
            catch
            {
                return fallback;
            }
        }

        private static double SafeGetDoubleProperty(object target, string prop, double fallback)
        {
            try
            {
                object val = target.GetType().InvokeMember(prop, BindingFlags.GetProperty, null, target, null);
                return val != null ? Convert.ToDouble(val) : fallback;
            }
            catch
            {
                return fallback;
            }
        }

        private static void SafeRelease(object comObj)
        {
            if (comObj != null && Marshal.IsComObject(comObj))
            {
                try { Marshal.ReleaseComObject(comObj); } catch { }
            }
        }
    }
}
