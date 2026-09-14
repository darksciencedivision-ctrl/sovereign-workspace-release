param(
    [Parameter(Position = 0)]
    [string]$Topic = ""
)

# route_topic.ps1 - SOVEREIGN Phase 5: Specialist Topic Router
# Standalone module. Dot-source into broker or run directly.
# Returns: "CODE" | "VISION" | "MATH" | "NONE"
#
# Matching: \b word-boundary regex.
#   - "decode" does NOT match \bcode\b
#   - "code."  DOES match \bcode\b (punctuation is a word boundary)
#   - "API"    DOES match \bapi\b (case-insensitive via ToLowerInvariant)
# First match wins. Order: CODE -> VISION -> MATH -> NONE.
#
# Usage (standalone):
#   powershell -ExecutionPolicy Bypass -File .\route_topic.ps1 -Topic "build a REST api"
#
# Usage (dot-source):
#   . .\route_topic.ps1
#   $type = Get-SpecialistType "implement a binary search"

function Get-SpecialistType([string]$topic) {
    if ([string]::IsNullOrWhiteSpace($topic)) { return "NONE" }

    $t = $topic.ToLowerInvariant()

    $codeKeywords = @(
        "code", "implement", "build", "function", "script", "debug",
        "algorithm", "class", "api", "refactor", "architecture"
    )
    foreach ($kw in $codeKeywords) {
        if ($t -match ("\b" + [regex]::Escape($kw) + "\b")) { return "CODE" }
    }

    $visionKeywords = @(
        "image", "video", "visual", "diagram", "screenshot",
        "frame", "chart", "photo"
    )
    foreach ($kw in $visionKeywords) {
        if ($t -match ("\b" + [regex]::Escape($kw) + "\b")) { return "VISION" }
    }

    $mathKeywords = @(
        "calculate", "derive", "prove", "equation", "integral",
        "matrix", "probability", "formula"
    )
    foreach ($kw in $mathKeywords) {
        if ($t -match ("\b" + [regex]::Escape($kw) + "\b")) { return "MATH" }
    }

    return "NONE"
}

# Allow direct execution: .\route_topic.ps1 -Topic "some topic"
if ($PSBoundParameters.ContainsKey("Topic") -and -not [string]::IsNullOrWhiteSpace($Topic)) {
    Get-SpecialistType -topic $Topic
}
