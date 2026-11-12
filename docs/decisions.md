# Decisions and the evidence behind them

The numbers on this page were measured on the two official files
(`input-backend.csv` and `input-backend.json`, both last modified on 8 January 2019),
on the running service, or with python-phonenumbers where section 2 says so. Where a
choice could reasonably have gone the other way, the other way and its cost are
written down.

## 1. Reading the bounding boxes

The README gives three boxes:

| Type | minlon | minlat | maxlon | maxlat |
|---|---|---|---|---|
| SPECIAL | -2.196998 | -46.361899 | -15.411580 | -34.276938 |
| SPECIAL | -19.766959 | -52.997614 | -23.966413 | -44.428305 |
| NORMAL | -26.155681 | -54.777426 | -34.016466 | -46.603598 |

Two things are wrong with them, and they do not call for the same answer.

### The "min" longitudes are greater than the "max" ones

In all three boxes `minlon > maxlon`. A literal `minlon <= lon <= maxlon` is never
true. Measured on the 2000 customers: 0 special, 0 normal, 2000 laborious, and the
`type` filter would be useless.

A rectangle is the same set of points whichever corner is named first, so each axis
is sorted before use (`BoundingBox.from_published`). This does not change the rule,
it only makes it applicable. Result: **4 special, 4 normal, 1992 laborious**.

### The labels look transposed

With the labels as published, the three boxes lie in the South Atlantic Ocean
(latitudes -34 to -55, longitudes -2 to -34). Read the other way round, with the
values labelled "lon" taken as latitudes, they become three rectangles over Brazil:

| Box | Latitude | Longitude | What is there |
|---|---|---|---|
| first SPECIAL | -15.4 to -2.2 | -46.4 to -34.3 | the Northeast |
| second SPECIAL | -24.0 to -19.8 | -53.0 to -44.4 | the state of São Paulo and its surroundings |
| NORMAL | -34.0 to -26.2 | -54.8 to -46.6 | Santa Catarina and Rio Grande do Sul |

The 2019 version of the README says the boxes mark the places where the company's
consultants are concentrated. In every box the first pair of values is the
north-west corner and the second pair the south-east corner when read as
"latitude, longitude". The likely story is that corner points were copied in that
order under names that say "longitude, latitude".

### What was implemented, and why

**The published labels, with sorted axes.** Values labelled `lon` are compared with
the longitude, values labelled `lat` with the latitude.

- The README is the contract. A reviewer who puts the code next to the README sees
  the same numbers under the same names.
- The data cannot settle it. The coordinates in the files are random points on the
  globe: only 44 of the 2000 fall inside the rectangle that contains Brazil, and they
  have no relation to the state of the customer (one customer whose state is
  Amazonas is located in the South Atlantic). Neither reading is geographically
  right for this data set.
- Sorting an axis keeps the rule. Swapping the axes replaces it with another one,
  which is a decision for whoever owns the rule. It is the first question to ask
  them.

What the other reading would change, on the official data:

| Reading | special | normal | laborious |
|---|---|---|---|
| Published labels, as written (min > max) | 0 | 0 | 2000 |
| **Published labels, axes sorted (implemented)** | **4** | **4** | **1992** |
| Axes transposed | 8 | 0 | 1992 |

Switching is a one-line change in `BoundingBox.from_published`. The tests that use
real customers or the README's numbers pin the current reading, in particular
`test_the_labels_are_applied_as_published_not_transposed`, so the switch cannot
happen by accident and would change those tests with it.

### Edges, priority, bad coordinates

- A point exactly on an edge is inside the box. Tested on the four corners and the
  four edges of each box, and one millionth of a degree outside each edge.
- The first matching rule wins, special before normal. The three published boxes do
  not overlap (a test checks it), so this order has no effect today. It is defined so
  that a future overlapping box has an answer.
- The README says laborious is "anyone not matching the above". Coordinates that are
  present but are not numbers, or are out of range, match no box: the customer is
  laborious and the values are served as received.
- Coordinates that are missing, null or blank are another case. The contract
  requires them, so the record is rejected (section 5) rather than served with
  invented values.

## 2. Phones: a format conversion, not a validity check

The rule is given by one example: `(86) 8370-9831` becomes `+558683709831`.

The brief for this project listed python-phonenumbers (the Python port of Google's
libphonenumber) among the references to study. It was installed and measured before
any phone code was written. On the 2000 numbers of the JSON file (the CSV holds the
same ones), with python-phonenumbers 9.0.43:

| Measure | Result |
|---|---|
| Shape of the numbers | all 2000 are `(99) 9999-9999`: 10 digits |
| `is_possible_number` | 2000 of 2000 |
| `is_valid_number` | **697 of 2000** (34.9 %) |
| E.164 output different from "+55 followed by the digits" | **213 of 2000** (10.7 %): 205 with a leading 0, 8 starting with 90 |
| Area code that is not one of the 67 in use in Brazil | 653 of 2000 (32.7 %) |
| The README's own example, `(86) 8370-9831` | possible, **not valid** |

Why, from the library's metadata for Brazil:

- The numbers are synthetic. A valid fixed-line number must start with 2 to 5 after
  the area code and a mobile number with 7 or 9. The README's example starts with 8.
- The library strips what it reads as a national prefix: a leading `0`, or `90`. For
  `(01) 5415-5648` it returns `+55154155648`, a different number from the one in the
  file.
- "Possible" only checks the length, and 8 to 11 digits are all possible in Brazil.
  `8370-9831` (no area code) and `(86) 8370-983` (one digit short) are both possible.
  It cannot be used to detect an incomplete number.

So a validity filter would empty two thirds of the phone lists and reject the
example the challenge uses to define the rule, and a blind `parse` then `format`
would silently rewrite one number in ten. Neither is what the rule asks.

**What `to_e164` does** (`src/transformers.py`, no dependency):

- 10 or 11 digits are a Brazilian national number: `+55` is added, digit for digit.
- A number that already carries 55 (`+55 ...` or `55 ...`) is not prefixed twice.
- A number written with `+` and another calling code keeps it, from 6 digits (the
  shortest complete numbers in libphonenumber's metadata, such as Austria's `+43`
  followed by 4 digits) to 15 (the E.164 maximum).
- Any other digit count is incomplete or overlong: **no number is produced** and the
  list is empty. Nothing is padded, nothing is cut.
- Letters in the value (an extension, a comment, two numbers in one cell) also give
  no number.
- A leading 0 is kept at 10 digits: area code plus 8 digits is the only reading that
  gives a complete number. At 11 digits it is refused: a trunk 0 plus 10 digits and
  an area code plus 9 digits are both complete readings, and they give different
  numbers.

Consequence, stated plainly: the API can return numbers that cannot be dialled,
because the source data contains them. In each file, 205 of the 2000 numbers have an
area code starting with 0, which no Brazilian area code does. They are converted
digit for digit like the others: checking area codes would be validation. All 4000
numbers of the official files are converted. If real data replaced the synthetic
files, validating against the numbering plan would be a change inside `to_e164` and
nowhere else.

To reproduce the measurement:

```python
import json, re, phonenumbers  # pip install phonenumbers==9.0.43

records = json.load(open("input-backend.json", encoding="utf-8"))["results"]
numbers = [record[field] for record in records for field in ("phone", "cell")]
parsed = [phonenumbers.parse(number, "BR") for number in numbers]
e164 = [phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.E164) for p in parsed]
print(sum(map(phonenumbers.is_valid_number, parsed)))  # 697
print(sum(out != "+55" + re.sub(r"\D", "", raw) for raw, out in zip(numbers, e164)))  # 213
```

## 3. The two files hold the same 1000 customers

Compared field by field, the 1000 CSV rows and the 1000 JSON records are the same
customers in the same order. The only differences are types: the CSV gives the
postcode and the ages as text.

The validator expects `totalCount` to be 2000 and the README announces 2000, so
"merge" is implemented as **concatenation, CSV first, then JSON, without
de-duplication**. The total is never written in the code: it is whatever the two
sources hold. A test loads the same customer from both files and expects it twice.

De-duplicating would give 1000 customers, or 999 if the e-mail were the key: one
e-mail address is shared by two different people inside each file. In a real
integration this is the first question to ask the partners.

## 4. All or nothing at startup

The data is loaded in the application's lifespan, before the server accepts a
request. If either source cannot be downloaded (network error, timeout, any status
other than 2xx), cannot be parsed, lacks one of the 22 expected CSV columns, or
yields no usable record, the lifespan raises and the process exits with code 3.
Checked on the real server: one CRITICAL line,
`startup aborted: csv source: download failed with ConnectError`, then uvicorn's
traceback, which shows neither the URL nor its query string. CI checks it on the
image twice: with the CSV unreachable, and with the JSON unreachable once the CSV
has been loaded.

There is no state in which the API answers with half of the data, and no retry loop
in the code: `restart: on-failure` in `docker-compose.yml`, or the orchestrator,
restarts the container. Redirects are followed and each phase of a download has a
timeout (`HTTP_TIMEOUT_SECONDS`, 10 seconds by default).

Because the server only answers once the load has succeeded, `GET /health` doubles
as a readiness check. It also reports how many customers were loaded and how many
records were rejected.

## 5. One strict contract, rejected records in plain sight

Three levels, three answers:

| Problem | Answer |
|---|---|
| A whole source is unusable | The service does not start (section 4). |
| A record cannot fill the output contract (a required field missing, null, blank or of the wrong type) | The record is rejected. It is counted, logged and reported by `/health`. The other records are served. |
| A field has a business fallback | Unknown gender and unknown state give `null`, a phone that cannot be converted is left out of its list, coordinates that are not numbers give `laborious`. The customer is kept. |

The alternative to rejecting a record was to make every field optional. Consumers
would then have to handle a `null` anywhere. A strict contract with a visible count
of what did not fit seemed the better trade: nothing is silent, and relaxing one
field later is a one-line change in `src/models.py`.

The official files produce no rejection: 2000 records in, 2000 customers out.

Log lines about a rejected record name the source, the position and the fields at
fault, never a value: `source=json record=2 rejected: location.postcode (int_parsing)`.
Only the first ten rejections of a source are detailed, the count is always exact.

There is no rejection threshold: a source where most records are rejected still
starts, with the count in `/health` and in the logs. Choosing a threshold is a
business decision that the challenge does not make.

A fallback can hide a change in the shape of a file. If a partner renamed the
`gender` column, every customer would get `null` and no record would be rejected.
The CSV is protected against that: its header must contain the 22 expected columns,
or the source is refused (other columns are ignored). The JSON file has no header,
so a key renamed in every record would go unnoticed for the fields that have a
fallback. This is a known limit.

## 6. Dates

The contract shows `"birthday": "1979-01-22T03:35:31Z"`. The source dates already
have this form. They are still parsed, for two reasons: a broken date should reject
the record instead of being served as text, and a date with another offset is
converted to UTC so that the output always ends with `Z`.

Only ISO 8601 date-times that carry an offset are accepted. Pydantic's own parser
also reads a bare number as a Unix timestamp. That would turn a shifted CSV column
(a phone number under a date header) into a plausible date, so the field uses an
explicit parser. A date that falls before year 1 or after year 9999 once converted
to UTC is refused like any other bad date. Fractions of a second are dropped, since
the contract has second resolution.

`dob.age` and `registered.age` are dropped by construction: only the dates are read.

## 7. Requests that are not valid

- An invalid value returns 422 with the name of the parameter and the reason. This
  is FastAPI's standard answer and it is described in the generated OpenAPI schema.
- An **unknown** parameter is also a 422. `?pagesize=50` answering with the default
  page would hide the typo from the caller.
- `region` and `type` accept exactly the lower-case values of the README.
- `pageSize` is limited to 100 (`MAX_PAGE_SIZE`). A larger value is refused, not
  silently reduced, so the caller always gets the page size it asked for.
- A page after the last one is a normal answer: 200, an empty list, and the same
  `totalCount`.
- Integers are read the way pydantic reads them: `1.0`, `+1` and `1_0` are accepted
  as 1, 1 and 10. A repeated parameter keeps its last value, which is FastAPI's
  behaviour. Neither seemed worth code of its own.

## 8. Smaller choices

- **Stable order.** Customers stay in load order. Nothing sorts them, so walking the
  pages returns each customer exactly once. Checked on the real data with pages of 7
  and of 100.
- **Surrounding spaces are removed** from text fields. 1398 of the 2000 street
  values of the official files end with a space. Inner spaces and case are untouched.
- **The state name is never rewritten.** It is normalised only to look up the region
  (case, accents, punctuation, repeated spaces). `"SÃO PAULO"` stays `"SÃO PAULO"`.
  Two-letter codes such as `SP` are not mapped: the files do not use them.
- **`postcode` is an integer** because the contract shows one. A real Brazilian
  postcode starting with 0 would lose that zero. The contract was followed and the
  wart is noted here.
- **No index.** Filtering scans the 2000 customers on each request, which takes
  about 0.2 ms on the development machine. An index per region and type would be
  more code than the problem deserves.
- **`async def` handlers.** They only read memory and never block the event loop.
- **Settings without pydantic-settings.** Five variables read once from the
  environment do not need another dependency. A plain pydantic model validates them
  and names the variable at fault.
- **Logs never contain the path or query string of a source URL.** A signed URL
  keeps its secret in the query string. httpx logs full URLs at INFO and puts them in
  its error messages, so its logger is raised to WARNING and its errors are not
  chained into the traceback. Two tests check it, one on the whole startup at DEBUG.
  At DEBUG, httpcore still logs the host and port it connects to.

## 9. Left out on purpose

A database, a cache, a background refresh of the data, a reload endpoint,
authentication, rate limiting, metrics, sorting options. None of them is asked for,
and each one would be more surface to test than the challenge itself.
