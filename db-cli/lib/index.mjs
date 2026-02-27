import { createClient } from "db-vendo-client";
import { profile as dbProfile } from "db-vendo-client/p/db/index.js";
import { parseTime } from "./time-parser.mjs";
import generateBahnDeUrl from "./bahn-url-builder.mjs";
import { displayResults } from "./journey-display.mjs";
import { handleStationSearch } from "./station-search.mjs";

export async function searchJourneys(options) {
  const {
    from,
    to,
    departure,
    arrival,
    results = 3,
    deutschlandticket,
  } = options;

  const client = createClient(dbProfile, "db-cli/1.0.0");

  // Search for stations
  const { fromLocation, toLocation } = await handleStationSearch(
    client,
    from,
    to,
  );

  // Prepare journey options
  const journeyOptions = {
    results,
    stopovers: true,
    tickets: true,
  };

  if (deutschlandticket) {
    journeyOptions.products = {
      nationalExpress: false, // no ICE
      national: false, // no IC/EC
      regionalExpress: true,
      regional: true,
      suburban: true,
      bus: true,
      ferry: true,
      subway: true,
      tram: true,
      taxi: false,
    };
    console.log("Filtering for Deutschlandticket-compatible transport only");
  }

  if (departure) {
    journeyOptions.departure = parseTime(departure);
    console.log(
      `Departure after: ${journeyOptions.departure.toLocaleString("de-DE")}`,
    );
  } else if (arrival) {
    journeyOptions.arrival = parseTime(arrival);
    console.log(
      `Arrival by: ${journeyOptions.arrival.toLocaleString("de-DE")}`,
    );
  }

  // Execute journey search
  console.log("Searching for journeys...\n");
  const result = await client.journeys(
    fromLocation.id,
    toLocation.id,
    journeyOptions,
  );

  if (result.journeys.length === 0) {
    console.log("No journeys found for the specified criteria.");
    return null;
  }

  // Generate bahn.de URL
  const bahnUrl = generateBahnDeUrl(
    fromLocation,
    toLocation,
    journeyOptions.departure,
    journeyOptions.arrival,
    { deutschlandticket },
  );

  // Display results
  displayResults(result.journeys, { fromLocation, toLocation }, bahnUrl);

  return result.journeys;
}

export { parseTime } from "./time-parser.mjs";
export { default as generateBahnDeUrl } from "./bahn-url-builder.mjs";
