"""Create illustrative state cards and synthetic travelers; no inference."""

import csv
import json
import sys
from pathlib import Path

STATES = [
    ("AL", "Alabama", "Gulf beaches, civil rights history, Southern food, and music heritage."),
    ("AK", "Alaska", "Glaciers, mountains, wildlife viewing, remote wilderness, and coastal cruises."),
    ("AZ", "Arizona", "Grand Canyon landscapes, desert hiking, red-rock scenery, and Southwestern cities."),
    ("AR", "Arkansas", "Ozark mountains, forests, rivers, hot springs, and small-town travel."),
    ("CA", "California", "Pacific beaches, major cities, national parks, wine regions, and varied landscapes."),
    ("CO", "Colorado", "Rocky Mountain hiking, skiing, mountain towns, and Denver's urban attractions."),
    ("CT", "Connecticut", "Historic New England towns, coastal villages, museums, and countryside drives."),
    ("DE", "Delaware", "Atlantic beaches, coastal towns, historic sites, and compact travel distances."),
    ("FL", "Florida", "Warm-weather beaches, theme parks, the Everglades, and Latin-influenced city culture."),
    ("GA", "Georgia", "Atlanta's museums and food, Savannah's historic streets, mountains, and coastal islands."),
    ("HI", "Hawaii", "Tropical beaches, volcanic landscapes, ocean activities, and Native Hawaiian culture."),
    ("ID", "Idaho", "Mountain wilderness, lakes, rafting rivers, hot springs, and small cities."),
    ("IL", "Illinois", "Chicago architecture, art museums, live music, diverse food, and prairie towns."),
    ("IN", "Indiana", "Indianapolis attractions, motorsports heritage, small towns, and Lake Michigan dunes."),
    ("IA", "Iowa", "Agricultural landscapes, river towns, state fairs, local food, and cycling routes."),
    ("KS", "Kansas", "Prairie scenery, Flint Hills, frontier history, small towns, and open-road travel."),
    ("KY", "Kentucky", "Bourbon heritage, horse country, cave exploration, Appalachian scenery, and bluegrass music."),
    ("LA", "Louisiana", "New Orleans jazz, Creole and Cajun food, historic neighborhoods, and bayou landscapes."),
    ("ME", "Maine", "Rocky coastline, Acadia scenery, fishing villages, lobster, and inland forests."),
    ("MD", "Maryland", "Chesapeake Bay, seafood, Baltimore museums, sailing towns, and Atlantic beaches."),
    ("MA", "Massachusetts", "Boston history and museums, Cape Cod beaches, island towns, and New England culture."),
    ("MI", "Michigan", "Great Lakes beaches, forested peninsulas, Detroit music heritage, and lakeside towns."),
    ("MN", "Minnesota", "Northern lakes, canoe wilderness, Minneapolis-Saint Paul arts, and outdoor recreation."),
    ("MS", "Mississippi", "Blues heritage, Southern food, river towns, literary history, and Gulf coastline."),
    ("MO", "Missouri", "St. Louis and Kansas City attractions, jazz and barbecue, river history, and Ozark scenery."),
    ("MT", "Montana", "Mountain parks, expansive landscapes, wildlife, hiking, and outdoor-oriented towns."),
    ("NE", "Nebraska", "Great Plains landscapes, pioneer history, Omaha attractions, and wildlife viewing."),
    ("NV", "Nevada", "Las Vegas entertainment, desert landscapes, mountain recreation, and resort experiences."),
    ("NH", "New Hampshire", "White Mountain hiking, lakes, fall foliage, skiing, and small New England towns."),
    ("NJ", "New Jersey", "Atlantic beach towns, boardwalks, diverse food, historic sites, and urban attractions."),
    ("NM", "New Mexico", "Desert landscapes, Pueblo and Hispanic cultural heritage, art towns, and regional food."),
    ("NY", "New York", "New York City arts and food, Hudson Valley towns, Adirondack recreation, and Niagara Falls."),
    ("NC", "North Carolina", "Blue Ridge mountains, Outer Banks beaches, barbecue, cities, and historic towns."),
    ("ND", "North Dakota", "Badlands scenery, Theodore Roosevelt National Park, prairie landscapes, and frontier history."),
    ("OH", "Ohio", "City museums, amusement parks, music and aviation history, and Lake Erie recreation."),
    ("OK", "Oklahoma", "Native American cultural institutions, Route 66 heritage, prairie scenery, and city museums."),
    ("OR", "Oregon", "Pacific coastline, forests, volcanoes, Portland food culture, and wine country."),
    ("PA", "Pennsylvania", "Philadelphia history, Pittsburgh museums, rural landscapes, and Appalachian recreation."),
    ("RI", "Rhode Island", "Ocean beaches, Newport architecture, Providence food and arts, and coastal sailing."),
    ("SC", "South Carolina", "Charleston history and food, Atlantic beaches, coastal islands, and Lowcountry culture."),
    ("SD", "South Dakota", "Black Hills, Badlands landscapes, Mount Rushmore, and Native American cultural history."),
    ("TN", "Tennessee", "Nashville country music, Memphis blues and soul, barbecue, and Great Smoky Mountains."),
    ("TX", "Texas", "Distinctive cities, barbecue and Tex-Mex, live music, Gulf beaches, and desert parks."),
    ("UT", "Utah", "Red-rock national parks, desert hiking, mountain skiing, and dramatic geological scenery."),
    ("VT", "Vermont", "Green Mountain scenery, small towns, fall foliage, local food, and skiing."),
    ("VA", "Virginia", "Colonial and Civil War history, Blue Ridge landscapes, museums, and Atlantic beaches."),
    ("WA", "Washington", "Seattle culture, Pacific coastline, islands, rainforests, and Cascade mountain recreation."),
    ("WV", "West Virginia", "Appalachian mountains, rafting, hiking, scenic railroads, and small-town heritage."),
    ("WI", "Wisconsin", "Lakes, dairy and brewing traditions, Milwaukee attractions, and family vacation towns."),
    ("WY", "Wyoming", "Yellowstone and Grand Teton landscapes, wildlife, mountain recreation, and Western heritage."),
]

PROFILES = [
    ("outdoors", "Outdoor explorer", "Your ideal vacation involves scenic hiking, national parks, wildlife, and "
     "mountain or wilderness landscapes. You prefer quiet natural places to big-city nightlife or theme parks."),
    ("city_culture", "City and culture traveler", "Your ideal vacation combines major art museums, architecture, "
     "walkable neighborhoods, theater, and varied restaurants. You enjoy cities and cultural variety more than remote nature."),
    ("beach_relaxation", "Beach and relaxation traveler", "Your ideal vacation offers attractive swimming beaches, "
     "ocean scenery, comfortable lodging, warm weather, and unhurried days. You would choose relaxation over strenuous hiking."),
    ("food_music", "Food and music traveler", "You travel for distinctive regional cooking, local food traditions, "
     "live music, and lively neighborhoods. You prize memorable cultural experiences over resort luxury or landmark checklists."),
    ("history", "History enthusiast", "You travel for historic districts, museums, architecture, and opportunities "
     "to learn about American history, including Indigenous cultures and civil rights. You enjoy thoughtful walking tours."),
    ("family", "Family vacation planner", "You plan vacations with two school-age children. You value a mix of "
     "engaging educational attractions, accessible outdoor fun, beaches or amusement parks, and manageable logistics. "
     "You prefer variety and practical family experiences over nightlife or difficult wilderness trips."),
]


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    assert len(STATES) == len({row[0] for row in STATES}) == 50
    with (output / "entrants.csv").open("x", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "name", "description"])
        writer.writerows(STATES)
    agents = [{"id": key, "traits": {"profile_name": name, "travel_preferences": preferences,
                "trip_assumptions": "You are choosing a first leisure visit to each state. Plan a one-week trip "
                "in the season that best suits your interests. Set aside travel distance from home and assume "
                "adequate funds for a normal vacation. Express your own travel preferences, not a generic tourism ranking."}}
              for key, name, preferences in PROFILES]
    # These profiles are authored above; they are not inferred or sampled people.
    from edsl import Agent, AgentList
    agent_path = output / "agent_list.ep"
    if agent_path.exists():
        raise FileExistsError(agent_path)
    AgentList([Agent(name=row["id"], traits=row["traits"]) for row in agents]).git.save(
        agent_path, message="Six hand-authored synthetic traveler profiles")
    (output / "model-parameters.json").write_text(json.dumps({"temperature": 0.7, "max_output_tokens": 4096}, indent=2) + "\n")
    (output / "design-notes.json").write_text(json.dumps({
        "purpose": "Live software demonstration of ranking all 50 U.S. states with six synthetic traveler profiles.",
        "entrant_cards": "Hand-authored illustrative summaries, not exhaustive destination research or current travel advice.",
        "criterion": "Rank the states by how much YOU, given your travel preferences, would like to visit for a "
                     "one-week leisure trip. Assume it would be your first visit to every state, choose each state's "
                     "best season for your interests, and disregard distance from home. Consider the supplied descriptions "
                     "and your stated preferences. Put the state you most want to visit FIRST.",
        "chunk_size": 5, "rounds": 5, "seed": 20260914, "agents": 6, "expected_calls": 390,
        "scope": "50 states; excludes Washington, D.C. and territories.",
        "interpretation": "Equal numbers of synthetic persona ballots, all generated by one model. "
                          "Not survey evidence about real travelers or a representative population.",
    }, indent=2) + "\n")
    print(json.dumps({"states": len(STATES), "profiles": len(PROFILES), "output": str(output), "agent_list": str(agent_path)}))


if __name__ == "__main__":
    main()
