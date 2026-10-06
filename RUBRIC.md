# Project 1 rubric: how we decide the right answer

These rules decide the answer key for every request, public and hidden. Your system sees the same card and description that we used.

## 1. What the system sees

Each request comes with five candidate games. For each game the system sees:

- BoardGameGeek's description of the game, word for word.
- A fact card with players, play time, minimum age, complexity (BoardGameGeek's weight, from 1 to 5, with the number of votes behind it), categories and mechanics. A field shown as "not listed" is either hidden on purpose or missing from BoardGameGeek. Either way, the card doesn't give it.

The system picks one game that meets every requirement, or declines when none does.

## 2. The right answer

For a given request, each of the five games is one of these:

- **Acceptable:** meets every requirement.
- **Breaks:** fails at least one requirement.
- **Can't tell:** fails none, but at least one can't be checked.

A correct pick is any acceptable game. If no game is acceptable, the correct answer is to decline. Picking a "can't tell" game is wrong.

**Unknown ("can't tell").** If a requirement can't be checked from either the card or the description, the game is "can't tell" for that requirement and must not be picked. What you know about the game from elsewhere doesn't count.

**Wishes are not requirements.** "Would be nice", "would be amazing" and "we'd love" mark a wish. A wish never makes a game unacceptable, and it never causes a decline.

## 3. Kinds of requirement

A request can ask for the kinds of requirement below. For each kind, the first part says what the request's wording means, and the second part says when a game fits.

### Players

**What the request means.** Count everyone who will play, including the writer when they say "I", "we" or "us".

- "Me and my brother" is 2.
- "Me, my husband and our three kids" is 5.
- "Game night with six friends" is 7: the writer plus six friends.

**When a game fits.** The game fits if the number is within the card's range. If the card doesn't list players, a number stated in the description counts. Only the base game counts. A count that needs a separately sold expansion does not: Dutch Blitz's card says 2–4, and the "up to eight players" in its description needs the separate Expansion Pack.

### Play time

**What the request means.** Phrases become a limit in minutes. "An hour", "an hour tops" and "about an hour" all mean at most 60. "Half an hour" means at most 30. "About" is read as the limit.

**When a game fits.** The game fits if its longest listed time fits, so "30–60 minutes" does not fit "at most 45". If the card doesn't list time, a play time stated in the description counts ("a twenty-minute game"). The time it takes to learn the rules does not: Ticket to Ride "can be learned in under 15 minutes", but that isn't its play time.

### Complexity

**What the request means.**

- "Easy rules", "simple", "beginners", "never play board games" and "casual players" mean light.
- "Deep strategy", "meaty" and "nothing light" mean heavy.
- "Not too simple, not too heavy" means medium.

**When a game fits.** BoardGameGeek's weight (1 to 5) is an average of player votes, and what a number means depends on who voted: a 2.0 family game and a 2.0 strategy game are not equally complex. So the weight decides on its own only at the extremes; otherwise it is one clue among several. The card shows the weight, how many votes it comes from, and BoardGameGeek's game types (family, party, children's, strategy, thematic, war, abstract).

Is it light?

- Yes if the weight is 1.3 or less; or the description says the rules are easy or simple; or it is a children's or party game; or it is a family game with a weight under 2.0.
- No if the weight is 4.0 or more; or the description says the rules are complex or for experienced players; or its only types are strategy, thematic, war or abstract and the weight is 2.5 or more.

Is it heavy?

- Yes if the weight is 4.0 or more; or the description says the rules are complex or for experienced players; or it is a strategy or war game, not also a family game, with a weight of 3.5 or more.
- No if the weight is 1.3 or less; or the description says the rules are easy or simple; or it is a children's, party or family game.

The extremes win over every other clue. If the clues point both ways, or none applies, the answer is "can't tell".

Is it medium?

- No if the game is light or heavy under the two questions above.
- Yes if it is neither, and its weight is between 2.0 and 3.5.
- Otherwise, can't tell. That covers a weight outside that band with no clue, and a card that doesn't list complexity.

What counts as description wording:

- Comparisons and genre labels count: "lighter than many similar games".
- Wording that says both, such as "easy to learn, but challenging to master", doesn't decide.
- Wording about something other than how hard the rules are doesn't count. That covers how hard the game is to win ("difficult to survive"), one part of the game (DungeonQuest's "even more complex and sprawling dungeon"), an optional variant (Bad Bones' "strategic variations for experts"), changes from another edition (Descent's "Simpler rules for determining line of sight"), and who the game is marketed to ("family game", "casual audience"). The card's game type covers the audience.

Examples:

- Jaipur, a family game at 1.46: light.
- Ticket to Ride, a family game at 1.82 with "elegantly simple gameplay": light.
- La Habana at 2.21, "shorter and lighter than many similar games": light.
- Wingspan, a family and strategy game at 2.47: can't tell for light, and not heavy.
- Res Arcana, a strategy game at 2.64: not light.
- Hyperborea, a strategy game at 3.16 described as "a light civilization game": the clues point both ways, so can't tell.
- Gaia Project, a strategy game at 4.39: heavy.

If the card doesn't list complexity, only description wording can decide; otherwise it's unknown.

### Cooperative or competitive

**What the request means.**

- "Together against the game", "team up against the game" and "as one team" mean cooperative.
- "Head to head" and "against each other" mean competitive.
- If the request says nothing, there is no requirement.

**When a game fits.** A game is cooperative if the players mostly play together against the game. That includes games with a possible hidden traitor (Shadows over Camelot: "one of the knights may be a traitor") and games where one player is named the best at the end (Castle Panic: "only one player will be declared the Master Slayer"). Teams that play against each other are competitive, even though teammates cooperate: Codenames, where "two teams compete". The card shows which: a game whose mechanics include "Cooperative Game" is cooperative, and a game without it is competitive.

### Age (hidden set only)

**What the request means.** "Our 8-year-old" means the game's minimum age must be 8 or lower.

**When a game fits.** The game fits if the card's minimum age is at or below the child's age. If the card doesn't list age, an age stated in the description counts ("ages 8 and up"). "Family game" does not.

### Things to avoid

**What the request means.**

- "No fighting" and "no combat" mean no fighting.
- "Nothing violent" means no violence, which also rules out fighting.
- "Nothing scary" and "nothing creepy" mean no horror.
- "No timers" and "no racing against the clock" mean no timer.
- "Nobody knocked out" and "nobody sitting out" mean no player elimination.

**When a game fits.** A game fits if it doesn't have the feature. A game has the feature if its card has the tag, or if its description shows the feature as part of the game under the definitions in section 4. A tag always counts. The description can add a feature the tags miss, but it can't remove a tag. The tags are:

- fighting: the "Fighting" category;
- violence: the "Wargame" category, or any fighting tag;
- horror: the "Horror" or "Zombies" category;
- timer: the "Real-time" category or the "Real-Time" mechanic;
- player elimination: the "Player Elimination" mechanic.

An empty category or mechanic list means BoardGameGeek lists no tags there. It is not a hidden field.

## 4. What counts as fighting, violence, horror, a timer and elimination

**The general rule for borderline cases**: judge what the description shows actually happens when people play. Don't go by isolated words, creature names, titles or outside knowledge of the game.

**Fighting and violence are separate**. A request for "no fighting" is about what players do in the game. A request for "nothing violent" is also about what the game is about.

**Fighting.** The players' characters or creatures fight other characters or creatures as something players do: they attack, battle or duel them. Armies, fleets or units attacking on a map feel like turn-based strategy rather than fighting, so they count as violence, not fighting.

- Counts:
  - Harry Potter: Hogwarts Battle: "fight against villains" (no tag).
  - Clank!: "Swords, which are used to fight the monsters" (no tag).
  - Nautilion: "recruit a heroic crew to vanquish the treacherous Darkhouse".
  - Kelp: "The Shark wins by successfully attacking the Octopus". Hunting and predation count only when one player's creature attacks another player's creature as a move; Neanderthal's "big game" and Oceans' food chain don't.
  - Marvel United: the Fighting tag, though the description never mentions fighting.
- Doesn't count:
  - Armies, fleets or units attacking on a map: Risk ("Attacking other players using a simple combat rule of comparing the highest dice rolled"), Jamaica ("there is a battle", resolved "by rolling a 'combat' die"). These count as violence.
  - Raiding, pillaging or conquering as a way to score: Raiders of the North Sea ("raiding unsuspecting settlements"), Catan Histories: Struggle for Rome ("pillaging cities"), Tawantinsuyu ("conquer villages"). These count as violence.
  - An assassination that is only the goal of a bluffing game: Crossfire ("protect or assassinate a Raxxon VIP"). It counts as violence.
  - Pandemic: "disease-fighting specialists" means treating diseases.
  - Splendor Duel: "fight over scarce access to Pearls" is competition for resources.
  - Spicy: the cats' fight is backstory; the game itself is a bluffing card game.
  - Figures of speech: Plague Inc., "battle against each other to spread their plagues"; Homeland, "combat the rising tide of global terrorism"; Portal, "fast-paced fight to the finish".
  - Attacks on something that isn't a character or creature: Cthulhu Dice, "Destroy your opponents' sanity!"
  - Contests that are only called duels or battles: Lizard Wizard's "Wizard's Duel" is an auction; the "Rock Paper Scissors battles" in We Didn't Playtest This at All.
  - A penalty that the game calls an attack: Catan's pirate, which takes your cards; in Timbuktu, "thieves attack the caravan and steal different goods".
  - Abstract captures, as in chess ("attack, defend").
  - A genre label alone, such as "dungeon crawler".

**Violence.** The game is about war, raiding, killing or other violence, whether or not players fight. Anything with fighting also counts as violence.

- Counts:
  - Everything under fighting above.
  - War and battles between armies, fleets or units: Risk, Jamaica, Endeavor ("colonization and war"; "Attacking steals a city from an opponent!"), The Hobbit ("how many shields they will contribute to battle").
  - Raiding, pillaging and conquest: Raiders of the North Sea, Raiders of Scythia ("raiding Settlements, taking Plunder"), Catan Histories: Struggle for Rome, Tawantinsuyu.
  - Killing as the goal: Crossfire.
  - The "Wargame" category, even if the description is silent.
- Doesn't count:
  - A penalty that the game calls an attack (Catan's pirate; Timbuktu's thieves).
  - Figures of speech and metaphors: Pandemic's "disease-fighting", Splendor Duel's "fight over scarce access to Pearls".
  - A grim backstory: Pandemic Legacy: Season 2's plague.

**Horror.** The game is meant to frighten or disturb. It presents horror creatures (vampires, zombies, werewolves, Cthulhu-style monsters), threatening ghosts or hauntings, being hunted, or gore as something frightening. A horror creature on its own doesn't make a game horror.

- Counts:
  - Dracula vs Van Helsing: Dracula "transforms all the inhabitants into vampires" (no tag).
  - Not Alone: "an alien entity picks up your scent and begins to hunt you" (tag as well).
  - Tides of Madness: the Horror tag, though the description never mentions horror.
  - Vast: The Mysterious Manor: "an adventure in a haunted house" with "murderous Skeletons".
- Doesn't count:
  - Pandemic Legacy: Season 2: a grim plague backstory is not horror.
  - Generic fantasy monsters and dungeons: Descent's "dark dungeons" and "horrors awaiting you beneath the surface".
  - Ghosts that are harmless or helpful: Hyperborea's "harmless but ominous ghosts"; the helpful ghost in Tajemnicze Domostwo.
  - Undead or demons as the enemies in heroic fantasy or comic games: Defenders of the Realm ("Orcs, Dragons, Demons and the Dead make haste towards Monarch City"); Bad Bones ("Terrible skeletons have arisen with a creepy clatter").
  - A horror word only in a licensed title: Legendary and Unmatched: Buffy the Vampire Slayer.
  - Realistic threats that aren't framed as frightening: Jaws ("the shark menaces swimmers"); Dark Moon's crew who "become paranoid, deceitful, and violent".
  - Cartoon spookiness in family games, not only children's games: Betrayal at Mystery Mansion, a Scooby-Doo game.
  - One horror character among many: BattleCON's "pair of tag-teaming werewolves".
- Cartoon spookiness in children's games, such as Catan: Junior ("Spooky Island", "Ghost Captain", ages 6+) and Ghost Blitz (a friendly house ghost), is not horror.
- King of Tokyo, where giant monsters smash a city (Fighting tag, no Horror tag), is not horror.
- Murder mysteries such as Clue are not horror.

**Timer.** Play involves racing a clock or a sand timer, or everyone playing at once as fast as they can.

- Counts:
  - 5-Minute Dungeon: "Once the five-minute timer starts" (tag as well).
  - Dutch Blitz: "Playing at the same time" (tag as well).
  - Cross Clues: the Real-time tag, though the description never mentions a timer.
  - Grabbing or running at the same moment: Dancing Eggs, "run around the table to try to be the first back to their seat".
  - A timed turn: Time's Up! Title Recall!, "as many titles as possible in 30 seconds".
- Doesn't count:
  - A countdown track that ends the game, or players choosing actions at the same time without racing.
  - Words about pace: Jaipur is "a fast-paced card game"; in Carcassonne "turns proceed quickly".
  - Racing as a theme: in Camel Up players bet on racing camels.
  - An optional timer the rules don't require: One Key "is best played with an app with a three-minute timer".

**Player elimination.** A player can be knocked out and has to sit and watch while the others keep playing, either for the rest of the game or for the rest of a round.

- Counts:
  - Love Letter: the Player Elimination tag, though the description never mentions it. A player who is caught sits out the rest of the round.
  - Deadwood 1876: "The last person alive is the winner!"
  - Elimination the rules make unavoidable, even though the description never says it: in Top Trumps, "The first player to win all the cards is the winner of the game", so with three or more players anyone who runs out of cards stops.
  - Sitting out for the rest of one round, as in Love Letter.
- Doesn't count:
  - Losing points, cards or pieces while still playing, including all of one's characters in play (BANG! The Duel).
  - A cooperative team losing together.
  - A two-player game where knocking the other player out ends the game, because nobody sits and watches (Catapult Feud, "a game of last person standing", for exactly 2 players).
  - A knocked-out player who keeps playing in another role: in Eaten by Zombies!, a player who runs out of cards becomes "a zombie, now trying to kill the other players".

**For any feature:**

- A feature counts if it appears in an optional variant or in one scenario in the box. In Shut the Box's scoring variant, players "go 'bust' and must drop out of the game". Unlock!: Epic Adventures includes a horror-movie adventure.
- When a description contradicts itself, the more detailed rule wins. Chairs says "you're out of the game", but then says "If the chairs fall on your turn, you must take all of the chairs that fell", so the player keeps playing and there is no elimination.
