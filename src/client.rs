//! Source-derived parcel search protocol. No delivery-change endpoints.
//! Rust port of yamato_cli/client.py — same requests, same errors.

use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::time::Duration;

pub const API_BASE: &str = "https://member.kms.kuronekoyamato.co.jp/api/";
pub const SEARCH_PATH: &str = "receive_parcel/v1/getParcelInfo";
const SEARCH_PAGE: &str = "https://member.kms.kuronekoyamato.co.jp/parcel/search";

#[derive(Debug)]
pub struct YamatoError {
    pub kind: &'static str,
    pub message: String,
    pub details: Map<String, Value>,
}

impl YamatoError {
    fn new(kind: &'static str, message: impl Into<String>) -> Self {
        YamatoError {
            kind,
            message: message.into(),
            details: Map::new(),
        }
    }

    fn detail(mut self, key: &str, value: Value) -> Self {
        self.details.insert(key.to_string(), value);
        self
    }

    pub fn validation(message: impl Into<String>) -> Self {
        Self::new("validation", message)
    }

    /// {"error": {"kind": ..., "message": ..., ...details}}
    pub fn json(&self) -> Value {
        let mut m = Map::new();
        m.insert("kind".to_string(), json!(self.kind));
        m.insert("message".to_string(), json!(self.message));
        for (k, v) in &self.details {
            m.insert(k.clone(), v.clone());
        }
        json!({ "error": Value::Object(m) })
    }
}

/// Accept ASCII digits with optional conventional grouping hyphens.
pub fn normalize_tracking_number(number: &str) -> Result<String, YamatoError> {
    let valid = if number.bytes().all(|b| b.is_ascii_digit()) {
        (11..=12).contains(&number.len())
    } else {
        let parts: Vec<&str> = number.split('-').collect();
        parts.len() == 3
            && parts[0].len() == 4
            && parts[1].len() == 4
            && (parts[2].len() == 3 || parts[2].len() == 4)
            && parts
                .iter()
                .all(|p| !p.is_empty() && p.bytes().all(|b| b.is_ascii_digit()))
    };
    if !valid {
        return Err(YamatoError::validation(
            "Tracking numbers must contain 11 or 12 ASCII digits, optionally grouped with hyphens.",
        ));
    }
    let normalized: String = number.chars().filter(|&c| c != '-').collect();
    // Check digit: int(normalized[:-1]) % 7 == int(normalized[-1])
    let body = &normalized[..normalized.len() - 1];
    let mut rem: u32 = 0;
    for b in body.bytes() {
        rem = (rem * 10 + u32::from(b - b'0')) % 7;
    }
    let last = normalized.as_bytes()[normalized.len() - 1] - b'0';
    if rem != u32::from(last) {
        return Err(YamatoError::validation(
            "Tracking number check digit does not match the Yamato modulo-7 rule.",
        ));
    }
    Ok(normalized)
}

/// Python truthiness for JSON values (used where the Python code does `x or []`).
fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().map(|f| f != 0.0).unwrap_or(false),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

fn or_empty_list(v: Option<&Value>) -> Value {
    match v {
        Some(v) if truthy(v) => v.clone(),
        _ => json!([]),
    }
}

/// One cookie-preserving HTTP session; requests are never retried.
pub struct YamatoClient {
    http: reqwest::blocking::Client,
    timeout: Duration,
    device_id: String,
    cookies: HashMap<String, String>,
}

impl YamatoClient {
    pub fn new(timeout_secs: f64) -> Result<Self, YamatoError> {
        if !timeout_secs.is_finite() || timeout_secs <= 0.0 {
            return Err(YamatoError::validation(
                "Timeout must be a positive finite number.",
            ));
        }
        let http = reqwest::blocking::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|e| YamatoError::new("transport", e.to_string()))?;
        Ok(YamatoClient {
            http,
            timeout: Duration::from_secs_f64(timeout_secs),
            device_id: uuid::Uuid::new_v4().to_string(),
            cookies: HashMap::new(),
        })
    }

    pub fn track(&mut self, numbers: &[String]) -> Result<Value, YamatoError> {
        let normalized: Vec<String> = numbers
            .iter()
            .map(|n| normalize_tracking_number(n))
            .collect::<Result<_, _>>()?;
        if normalized.is_empty() {
            return Err(YamatoError::validation(
                "Supply at least one tracking number. Use probe for an empty-list request.",
            ));
        }
        if normalized.len() > 100 {
            return Err(YamatoError::validation(
                "Search accepts at most 100 tracking numbers.",
            ));
        }
        self.search(&normalized)
    }

    /// Submit an empty shipment list only. Acceptance does not prove tracking works.
    pub fn probe(&mut self) -> Result<Value, YamatoError> {
        self.search(&[])
    }

    pub fn detail(&mut self, number: &str) -> Result<Value, YamatoError> {
        let okj = normalize_tracking_number(number)?;
        self.request(
            "receive_parcel/v1/getParcelDetailInfo",
            json!({ "nmtJho": { "okjNo": okj, "uktHasKbn": "01" } }),
            "NRCWBRP0610",
        )
    }

    pub fn slots(&mut self, number: &str) -> Result<Value, YamatoError> {
        let body = self.detail(number)?;
        let result = body
            .get("result")
            .filter(|r| r.is_object())
            .ok_or_else(|| {
                YamatoError::new("protocol", "Expected detail result to be an object.")
                    .detail("response", body.clone())
            })?;
        let eligibility = result.get("henKahHntKkaJho").filter(|e| e.is_object());
        let flag = eligibility
            .and_then(|e| e.get("jtkNaiUktHenKahFlg"))
            .cloned()
            .unwrap_or(Value::Null);
        Ok(json!({
            "nmtJho": result.get("nmtJho").cloned().unwrap_or(Value::Null),
            "eligible_for_date_change": flag == json!("1"),
            "henKahHntKkaJho": result.get("henKahHntKkaJho").cloned().unwrap_or(Value::Null),
            "date_change_eligibility": flag,
            "scnHttKboDayJhoLst": or_empty_list(result.get("scnHttKboDayJhoLst")),
            "scnHttKboBsyJhoLst": or_empty_list(result.get("scnHttKboBsyJhoLst")),
            "note": "Raw server options only. Date changes require eligible_for_date_change=true and date/time availability flags equal to 1.",
        }))
    }

    fn search(&mut self, numbers: &[String]) -> Result<Value, YamatoError> {
        let list: Vec<Value> = numbers
            .iter()
            .map(|n| json!({ "okjNo": n, "uktHasKbn": "01", "kroMchFlg": "0" }))
            .collect();
        self.request(
            SEARCH_PATH,
            json!({ "myNmtJho": { "nmtJhoLst": list } }),
            "NRCWBRP0200",
        )
    }

    fn request(
        &mut self,
        path: &str,
        mut payload: Value,
        page_id: &str,
    ) -> Result<Value, YamatoError> {
        let mut ktu = json!({
            "iriTs": chrono::Utc::now().format("%Y-%m-%dT%H:%M:%S%.3f+00:00").to_string(),
            "tnmSbtCd": "1",
        });
        if let Some(ws) = self.cookies.get("web_service_id") {
            ktu["kroId"] = json!(ws);
        }
        payload["ktuJho"] = ktu;

        let url = format!(
            "{}{}?X-NEKO-TRACE={}&X-NEKO-DEVICE={}",
            API_BASE,
            path,
            uuid::Uuid::new_v4(),
            self.device_id
        );
        let mut rb = self
            .http
            .post(&url)
            .header("X-SYSTEM-ID", "NRC")
            .header("X-PG_ID", page_id)
            .header("X-PG-ID", page_id)
            .header("Accept", "application/json")
            .header("Origin", "https://member.kms.kuronekoyamato.co.jp")
            .header("Referer", SEARCH_PAGE)
            .timeout(self.timeout);
        if let Some(token) = self.cookies.get("token") {
            rb = rb.header("Authorization", format!("Bearer {token}"));
        }
        if let Some(xsrf) = self.cookies.get("XSRF-TOKEN") {
            rb = rb.header("X-XSRF-TOKEN", xsrf);
        }
        if !self.cookies.is_empty() {
            let cookie = self
                .cookies
                .iter()
                .map(|(k, v)| format!("{k}={v}"))
                .collect::<Vec<_>>()
                .join("; ");
            rb = rb.header("Cookie", cookie);
        }

        let resp = rb
            .json(&payload)
            .send()
            .map_err(|e| YamatoError::new("transport", e.to_string()))?;

        for v in resp.headers().get_all("set-cookie") {
            if let Ok(s) = v.to_str() {
                if let Some((name, rest)) = s.split_once('=') {
                    let value = rest.split(';').next().unwrap_or("");
                    self.cookies.insert(name.to_string(), value.to_string());
                }
            }
        }

        let status = resp.status().as_u16();
        let text = resp
            .text()
            .map_err(|e| YamatoError::new("transport", e.to_string()))?;
        let body: Value = serde_json::from_str(&text).unwrap_or(Value::String(text));
        let ctx = |e: YamatoError| e.detail("http_status", json!(status)).detail("response", body.clone());

        if !(200..300).contains(&status) {
            return Err(ctx(YamatoError::new(
                "http",
                "Yamato returned an unsuccessful HTTP status.",
            )));
        }
        if !body.is_object() {
            return Err(ctx(YamatoError::new(
                "protocol",
                "Expected a JSON object from Yamato.",
            )));
        }
        if body.get("errors").map(truthy).unwrap_or(false) {
            return Err(ctx(YamatoError::new(
                "application",
                "Yamato returned application errors.",
            )));
        }
        if body.get("result").is_none() {
            return Err(ctx(YamatoError::new(
                "protocol",
                "Yamato response did not contain result.",
            )));
        }
        Ok(body)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_plain_and_hyphenated() {
        assert_eq!(normalize_tracking_number("123456789013").unwrap(), "123456789013");
        assert_eq!(normalize_tracking_number("1234-5678-9013").unwrap(), "123456789013");
        assert_eq!(normalize_tracking_number("12345678903").unwrap(), "12345678903");
    }

    #[test]
    fn rejects_bad_format_and_check_digit() {
        assert!(normalize_tracking_number("123").is_err());
        assert!(normalize_tracking_number("1234-567-8901").is_err());
        assert!(normalize_tracking_number("abcdefghijk").is_err());
        // same digits, wrong last digit
        assert!(normalize_tracking_number("123456789010").is_err());
        assert!(normalize_tracking_number("1234-5678-9010").is_err());
    }

    #[test]
    fn empty_and_over_100_rejected() {
        let mut c = YamatoClient::new(5.0).unwrap();
        assert!(c.track(&[]).is_err());
        let many: Vec<String> = (0..101).map(|_| "123456789013".to_string()).collect();
        assert!(c.track(&many).is_err());
    }

    #[test]
    fn truthy_matches_python() {
        assert!(!truthy(&json!(null)));
        assert!(!truthy(&json!(false)));
        assert!(!truthy(&json!(0)));
        assert!(!truthy(&json!("")));
        assert!(!truthy(&json!([])));
        assert!(!truthy(&json!({})));
        assert!(truthy(&json!("x")));
        assert!(truthy(&json!([1])));
        assert!(truthy(&json!({"a":1})));
    }
}
