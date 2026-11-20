# DayFlow: make healthy choices fit your day

## The idea

Busy schedules can make exercise and healthy eating feel like extra tasks. DayFlow aims to turn the time and places already in someone's day into opportunities to move, eat well and discover their city.

Imagine finishing a class with an hour before your next appointment. DayFlow could suggest walking there, taking a small detour past a garden, and finding a suitable meal nearby—all while leaving enough time to arrive. The goal is to make healthy habits feel rewarding and realistic, not like another rigid plan.

## What the prototype does today

The current Pippa draft accepts a starting place, destination and available time, and optionally a buffer, maximum detour and weight. It looks up a walking route, checks whether it fits, and tries to find a scenic stop within the time limit. It offers a walking map link and, when weight is supplied and a route is available, an approximate estimate of active calories for the proposed walk. Mapping and scenery services can be unavailable, and the result says when a route or stop could not be checked. Directions in Google Maps can differ from the estimate. The prototype can also find nearby restaurants and gyms with map-search links, and calculate BMI from height and weight supplied for a single request. Venue listings are not verified health recommendations, and BMI is only a rough screening measure.

## What we want to build next

- **A day-aware plan:** with permission, use calendar times and locations to suggest walks, workouts and meals around existing commitments.
- **Explore while moving:** add photos, accessible routes and community-submitted discoveries to make walking something to look forward to.
- **Food that fits:** recommend nearby restaurants and specific dishes when trustworthy menu information is available; let users record meals and eventually use food photos as an approximate aid.
- **Personal guidance over time:** use optional profile details and food and activity records to identify patterns and suggest realistic adjustments. Estimates would be clearly labelled, with user control over personal data.
- **Local partnerships:** collaborate with restaurants and gyms on suitable offers that give users convenient choices and help local businesses reach people.

These are the product vision, not features already delivered by the prototype. Photo-based nutrition estimates and personal recommendations would require careful validation, privacy controls and appropriate sources; they would not replace medical or dietary advice.

## Why it matters

Instead of asking people to reorganise their lives around a separate fitness plan, DayFlow aims to meet them where they already are: between classes, meetings and the places they want to go.
