"""Built-in dictionaries used when Faker is not installed.

These exist purely to keep the redaction pipeline working in environments
where the optional ``[pii-v2-redaction]`` extra hasn't been installed —
the pipeline still produces same-length mocks, just from a smaller pool.
"""

from __future__ import annotations

# Curated lists chosen for length variety + UK-banking plausibility.
FIRST_NAMES = [
    "Aiden", "Alex", "Ali", "Amelia", "Amy", "Anna", "Arjun", "Ava", "Beth", "Cara",
    "Charlie", "Chloe", "Daniel", "Dev", "Diya", "Eli", "Ella", "Emily", "Emma", "Eva",
    "Finn", "Freya", "Grace", "Harry", "Henry", "Holly", "Ibrahim", "Isla", "Jack",
    "James", "Jasmine", "Jay", "Jen", "John", "Jordan", "Joseph", "Joshua", "Kate",
    "Kavya", "Kim", "Layla", "Leo", "Lewis", "Liam", "Lily", "Lucas", "Luna", "Mason",
    "Maya", "Mia", "Mohammed", "Nathan", "Nia", "Noah", "Olivia", "Omar", "Oscar", "Pam",
    "Phoebe", "Priya", "Rio", "Robin", "Rohan", "Ruby", "Ryan", "Sam", "Sara", "Sasha",
    "Sienna", "Sky", "Sofia", "Tara", "Tariq", "Theo", "Thomas", "Tom", "Tyler", "Uma",
    "Vera", "Victor", "Wade", "Willa", "William", "Yusuf", "Zac", "Zara", "Zoe",
]

LAST_NAMES = [
    "Adams", "Ali", "Allen", "Anderson", "Bailey", "Baker", "Bell", "Bennett", "Brown",
    "Carter", "Clark", "Collins", "Cook", "Cooper", "Cox", "Davies", "Davis", "Edwards",
    "Evans", "Fisher", "Foster", "Gray", "Green", "Hall", "Harris", "Hill", "Howard",
    "Hughes", "Jackson", "James", "Jenkins", "Johnson", "Jones", "Kelly", "Khan", "King",
    "Lee", "Lewis", "Lloyd", "Marshall", "Martin", "Mason", "Miller", "Mitchell",
    "Moore", "Morgan", "Morris", "Murphy", "Murray", "Nelson", "Owen", "Palmer", "Parker",
    "Patel", "Perry", "Phillips", "Powell", "Price", "Reed", "Reid", "Richards",
    "Roberts", "Robinson", "Rogers", "Russell", "Saunders", "Scott", "Shah", "Shaw",
    "Singh", "Smith", "Stewart", "Taylor", "Thomas", "Thompson", "Turner", "Walker",
    "Ward", "Watson", "White", "Wilkinson", "Williams", "Wilson", "Wood", "Wright",
    "Young",
]

ORGANISATIONS = [
    "Acme Ltd", "Ankle & Co", "Apex Trust", "BankCorp", "Beacon LLP", "Bluefin Bank",
    "Caldwell Ltd", "Cascade", "Central Mutual", "Citizens UK", "Civic Co", "Clearwater",
    "Cobalt Bank", "Coral Holdings", "Cornerstone", "Cygnet Group", "Delphi", "Drift",
    "Eastward", "Edgewater", "Emerald LLP", "Equinox Co", "Everbridge", "Falcon Bank",
    "Fennec", "Fjord Capital", "Forge & Co", "Galaxy Trust", "Gilded Co", "Glimmer Ltd",
    "Grange Bank", "Harbour Ltd", "Haven Group", "Helix Bank", "Hex Capital", "Indigo",
    "Inland LLP", "Ironclad", "Ivory Group", "Jade Trust", "Jasmine Co", "Karma Bank",
    "Kestrel Ltd", "Lantern Co", "Larkspur", "Linden Bank", "Luma Trust", "Magpie Co",
    "Marble LLP", "Meadow Bank", "Mercury Co", "Nimbus Bank", "North & Co", "Oakhill",
    "Onyx Trust", "Orion Bank", "Pebble & Co", "Pinewood", "Plume Capital", "Quartz Ltd",
    "Ravenwood", "Resolute", "Riverstone", "Saffron Bank", "Sage Capital", "Sapphire",
    "Serene LLP", "Shoreline", "Silver Bank", "Solace Co", "Sparrow & Co", "Spruce",
    "Stellar Ltd", "Sterling Bank", "Stone & Co", "Suncrest", "Tamarind", "Terra LLP",
    "Thistle Bank", "Tidal & Co", "Topaz Group", "Trident Ltd", "Twilight Co", "Umber",
    "Vanguard", "Velvet Bank", "Verdant LLP", "Vesper & Co", "Vivid Ltd", "Walnut Bank",
    "Wisteria", "Yarrow Ltd", "Zenith Trust", "Zephyr & Co", "Zinc Group",
]

EMAIL_LOCAL_PARTS = [
    "alex", "amy", "anna", "ben", "bea", "cara", "chris", "dan", "deb", "dev",
    "emma", "eli", "evan", "finn", "gail", "grace", "hari", "hugo", "ian", "ivy",
    "jack", "jen", "jess", "jill", "john", "jude", "kai", "kim", "kira", "leo",
    "lily", "luna", "max", "mia", "nia", "noah", "olly", "ollie", "owen", "pam",
    "paul", "phil", "rio", "rob", "rosa", "ruby", "sam", "saul", "sky", "stan",
    "tara", "theo", "tim", "tom", "uma", "vera", "vic", "wade", "wes", "will",
    "yaz", "zac", "zoe",
]

EMAIL_DOMAINS_BY_LEN: dict[int, list[str]] = {
    # Map domain length → list of plausible same-length domain strings.
    # ``len`` here = number of chars in the full domain (no @).
    7: ["m.co.uk", "mail.co", "post.uk"],
    8: ["mail.com", "mail.org", "post.com"],
    9: ["bank.uk", "trust.com", "mailco.uk"],
    10: ["mail.co.uk", "post.co.uk", "bank.com.uk", "trust.co.uk"],
    11: ["bank.co.uk", "trust.co.uk", "civic.co.uk"],
    12: ["sample.co.uk", "secure.co.uk", "lender.co.uk"],
    13: ["example.co.uk", "general.co.uk", "midland.co.uk"],
    14: ["citizens.co.uk", "domestic.co.uk", "northern.co.uk"],
    15: ["financial.co.uk", "investing.co.uk", "savings1.com.uk"],
    16: ["financial1.co.uk", "shorelines.co.uk", "newcastle.co.uk"],
}

STREETS = [
    "Acacia Avenue", "Acorn Road", "Albert Street", "Anvil Lane", "Aspen Drive",
    "Beech Road", "Belmont Road", "Birch Avenue", "Brook Lane", "Cardinal Road",
    "Cedar Lane", "Cherry Lane", "Chestnut Avenue", "Church Lane", "Cliff Road",
    "Clyde Street", "Corner Lane", "Cottage Lane", "Crescent Way", "Cypress Drive",
    "Daisy Lane", "Dale Road", "Down Lane", "Eagle Avenue", "Elm Avenue",
    "Fairfield Road", "Falcon Way", "Fern Walk", "Field Lane", "Forest Avenue",
    "Garden Road", "Glen Road", "Glenmore Avenue", "Grange Avenue", "Green Lane",
    "Harbour Walk", "Harrow Road", "Hawthorn Drive", "Hazel Avenue", "Heath Road",
    "High Street", "Holly Drive", "Honey Lane", "Hope Street", "Ivy Lane",
    "Jasmine Walk", "Kestrel Lane", "King's Road", "Laurel Avenue", "Lavender Lane",
    "Lime Avenue", "Lupin Lane", "Magnolia Way", "Maple Drive", "Market Lane",
    "Meadow Lane", "Mill Road", "Moor Lane", "North Road", "Oak Avenue",
    "Olive Walk", "Orchard Road", "Park Lane", "Pine Drive", "Plum Lane",
    "Poplar Drive", "Quartz Avenue", "Queen's Road", "Rose Lane", "Rowan Drive",
    "Sage Lane", "Salt Road", "Silver Lane", "South Lane", "Spring Road",
    "Station Road", "Stone Avenue", "Sugar Lane", "Sweet Lane", "Tamarind Way",
    "Tudor Avenue", "Tulip Walk", "Vine Lane", "Walnut Drive", "Watson Avenue",
    "West Road", "Willow Drive", "Wood Lane", "Yew Avenue",
]

CITIES = [
    "Bath", "Bedford", "Belfast", "Birmingham", "Bradford", "Brighton", "Bristol",
    "Cambridge", "Cardiff", "Carlisle", "Chester", "Chichester", "Coventry", "Derby",
    "Dundee", "Durham", "Edinburgh", "Exeter", "Glasgow", "Gloucester", "Hereford",
    "Hull", "Inverness", "Ipswich", "Lancaster", "Leeds", "Leicester", "Lincoln",
    "Liverpool", "London", "Manchester", "Newcastle", "Newport", "Norwich", "Nottingham",
    "Oxford", "Perth", "Peterborough", "Plymouth", "Portsmouth", "Preston", "Reading",
    "Salford", "Salisbury", "Sheffield", "Southampton", "Stirling", "Stoke", "Sunderland",
    "Swansea", "Truro", "Wakefield", "Wells", "Westminster", "Winchester", "Wolverhampton",
    "Worcester", "York",
]
