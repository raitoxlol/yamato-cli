//! JSON command-line interface. Rust port of yamato_cli/__main__.py.

mod client;

use clap::{Parser, Subcommand};
use client::YamatoClient;
use std::process::ExitCode;

#[derive(Parser)]
#[command(name = "yamato", version, about = "Experimental read-only Yamato parcel search")]
struct Cli {
    /// HTTP timeout in seconds, default 20
    #[arg(long, default_value_t = 20.0)]
    timeout: f64,
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Search only tracking numbers you are authorized to access
    Track {
        /// Tracking numbers (11/12 digits, optionally hyphen-grouped)
        numbers: Vec<String>,
    },
    /// Submit an empty shipment list, without querying a parcel
    Probe,
    /// Read parcel details
    Detail {
        /// Tracking number
        number: String,
    },
    /// Read server-returned delivery options
    Slots {
        /// Tracking number
        number: String,
    },
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let mut client = match YamatoClient::new(cli.timeout) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("{}", e.json());
            return ExitCode::from(2);
        }
    };
    let result = match &cli.cmd {
        Cmd::Probe => client.probe(),
        Cmd::Track { numbers } => client.track(numbers),
        Cmd::Detail { number } => client.detail(number),
        Cmd::Slots { number } => client.slots(number),
    };
    match result {
        Ok(v) => {
            println!("{}", serde_json::to_string(&v).unwrap_or_default());
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("{}", e.json());
            ExitCode::from(2)
        }
    }
}
