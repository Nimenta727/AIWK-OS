namespace AIWorkstation.Core;

/// <summary>
/// Restricts embedded third-party frontends to explicitly configured loopback endpoints.
/// This is not a sandbox: a local web service has its own trust and permission boundary.
/// </summary>
public static class LocalFrontendEndpoint
{
    public const string T3Default = "http://127.0.0.1:3773/";
    public const string OpenClawDefault = "http://127.0.0.1:18789/";

    public static bool TryParse(string? input, out Uri? endpoint)
    {
        endpoint = null;
        if (string.IsNullOrWhiteSpace(input) || input.Length > 2048 ||
            !Uri.TryCreate(input.Trim(), UriKind.Absolute, out var candidate))
            return false;

        if (!string.Equals(candidate.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase) &&
            !string.Equals(candidate.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
            return false;
        if (candidate.Host is not ("localhost" or "127.0.0.1" or "::1" or "[::1]") ||
            !string.IsNullOrEmpty(candidate.UserInfo) ||
            !string.IsNullOrEmpty(candidate.Query) ||
            !string.IsNullOrEmpty(candidate.Fragment))
            return false;
        if (candidate.Port < 1 || candidate.Port > 65535) return false;
        endpoint = candidate;
        return true;
    }

    public static bool IsWithinOrigin(Uri requested, Uri trusted)
    {
        return string.Equals(requested.Scheme, trusted.Scheme, StringComparison.OrdinalIgnoreCase) &&
            string.Equals(requested.Host, trusted.Host, StringComparison.OrdinalIgnoreCase) &&
            requested.Port == trusted.Port &&
            string.IsNullOrEmpty(requested.UserInfo);
    }
}
