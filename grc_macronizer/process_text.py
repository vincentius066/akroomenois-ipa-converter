import re
import betacode.conv
from grc_macronizer import Macronizer
from vowel_library import BETACODE_TO_IPA

macronizer = Macronizer(make_prints=True)

def preprocess_punctuation(text):
    """
    Removes square brackets, converts specific punctuation to dots,
    leaves commas untouched, and normalizes consecutive dots.
    """
    # Remove square brackets
    text = text.replace('[', '').replace(']', '')
    
    # Convert listed punctuation into dots. 
    # Target: · ; : ( ) " ' “ ” ‘ ’ — – ? ! « »
    punct_to_dot = re.compile(r'[·;:\(\)"\'“”‘’—–?!«»]')
    text = punct_to_dot.sub('.', text)
    
    # Normalize multiple adjacent dots to a single dot
    text = re.sub(r'\.+', '.', text)
    
    return text

def betacode_to_ipa(beta_text):
    """Converts Beta Code to IPA sequentially based on BETACODE_TO_IPA dict.
    Wraps converted IPA in brackets [...] and skips anything already in brackets.
    """
    for beta, ipa in BETACODE_TO_IPA.items():
        # Match EITHER existing bracketed content OR the beta code pattern
        pattern = re.compile(r'(\[[^\]]*\])|' + re.escape(beta))
        
        def replace_match(match):
            # If group 1 matched, it's inside brackets — return untouched
            if match.group(1):
                return match.group(1)
            # Otherwise, convert to IPA and wrap in brackets
            return f"[{ipa}]"
        
        beta_text = pattern.sub(replace_match, beta_text)
        
    return beta_text

def apply_syllabification(ipa_text):
    """
    Takes bracketed IPA text, drops punctuation, classifies V/C, 
    places syllable dots according to consonant cluster rules, 
    processes word boundaries for elision/ties, and removes the brackets.
    """
    # Step 0: Tokenize the input, removing punctuation but keeping brackets, spaces, and pauses
    tokens = []
    in_bracket = False
    current_val = ""
    
    for char in ipa_text:
        if char == '[':
            in_bracket = True
            current_val = ""
        elif char == ']':
            in_bracket = False
            if current_val:
                # Step 1: Detect if proto-syllable is a vowel or a consonant
                vowels = {'a', 'á', 'à', 'ǎ', 'â', 'e', 'é', 'è', 'ě', 'ê', 'i', 'í', 'ì', 'ǐ', 'î', 'o', 'ó', 'ò', 'ǒ', 'ô', 'u', 'ù', 'ǔ', 'û', 'y', 'ý', 'ỳ', 'y̌', 'ŷ', 'ɔ', 'ɔ̀', 'ɔ̌', 'ɔ̂', 'ɛ', 'ɛ̀', 'ɛ̌', 'ɛ̂'}
                is_v = any(v in current_val for v in vowels)
                tokens.append({'type': 'V' if is_v else 'C', 'val': current_val})
        elif in_bracket:
            current_val += char
        elif char.isspace():
            # Keep spaces to detect word divisions
            if tokens and tokens[-1]['type'] == 'S':
                tokens[-1]['val'] += char  # Collapse adjacent spaces if necessary
            else:
                tokens.append({'type': 'S', 'val': char})
        elif char == '|':
            # Keep pauses to detect chunk divisions
            if tokens and tokens[-1]['type'] == 'P':
                tokens[-1]['val'] += char  # Collapse || into a single token
            else:
                tokens.append({'type': 'P', 'val': char})
        else:
            # Characters outside brackets that aren't spaces or pipes are safely removed.
            pass

    # Find the indices of all Vowel tokens
    v_indices = [i for i, t in enumerate(tokens) if t['type'] == 'V']
    
    # Step 2: Place dots between consonant groups adjacent to multiple vowels.
    # We iterate backwards so inserting dots doesn't shift the indices of upcoming groups.
    if len(v_indices) >= 2:
        for i in range(len(v_indices) - 1, 0, -1):
            start_v_idx = v_indices[i-1]
            end_v_idx = v_indices[i]
            
            # The tokens strictly between two vowels
            block = tokens[start_v_idx+1 : end_v_idx]
            
            # If there is a pause in this block, chunks are treated separately.
            # We skip syllable dot placement for this specific interval.
            if any(t['type'] == 'P' for t in block):
                continue
            
            # Find all consonants inside this specific block
            c_items = [(idx, t) for idx, t in enumerate(block) if t['type'] == 'C']
            num_c = len(c_items)
            
            if num_c == 0:
                # Rule for 0 consonants: add a dot between the two vowels
                block.insert(0, {'type': 'DOT', 'val': '.'})
            elif num_c == 1:
                # Rule 2a: One consonant -> dot is before the consonant
                dot_idx = c_items[0][0]
                block.insert(dot_idx, {'type': 'DOT', 'val': '.'})
                
            elif num_c == 2:
                # Rule 2b: Two consonants
                c1_idx, c1 = c_items[0]
                c2_idx, c2 = c_items[1]
                combo = c1['val'] + c2['val']
                
                group_g = {
                    'pr', 'pl', 'pn', 'pm', 'tr', 'tl', 'tn', 'tm', 'kr', 'kl', 'kn', 'km',
                    'pʰr', 'pʰl', 'pʰn', 'pʰm', 'tʰr', 'tʰl', 'tʰn', 'tʰm', 'kʰr', 'kʰl', 'kʰn', 'kʰm',
                    'br', 'dr', 'gr'
                }
                
                # Check if there is a word division (space token) strictly between C1 and C2
                has_space = any(t['type'] == 'S' for t in block[c1_idx+1 : c2_idx])
                
                if combo in group_g and not has_space:
                    # (ii) Part of group AND no word division -> dot before first consonant
                    block.insert(c1_idx, {'type': 'DOT', 'val': '.'})
                else:
                    # (i) Not part of group OR (ii) Part of group but has space -> dot between both
                    block.insert(c1_idx + 1, {'type': 'DOT', 'val': '.'})
                    
            else:
                # Rule 2c: Three or more consonants
                def get_sonority(val):
                    if val in ['r', 'l']: return 5
                    if val in ['m', 'n']: return 4
                    if val == 's': return 3
                    if val == 'r̥ʰ': return 2
                    return 1
                
                scores = [get_sonority(c['val']) for _, c in c_items]
                min_score = min(scores)
                
                # Find the FIRST consonant with the lowest score
                target_c_idx_in_list = scores.index(min_score)
                target_c_idx_in_block = c_items[target_c_idx_in_list][0]
                
                # Placed directly AFTER this consonant
                block.insert(target_c_idx_in_block + 1, {'type': 'DOT', 'val': '.'})
            
            # Replace the old block with the newly dotted block in our token list
            tokens[start_v_idx+1 : end_v_idx] = block

    # Step 3: Diphthong offglide shift before a vowel syllable
    target_vowels = {'a', 'á', 'à', 'ǎ', 'â', 'o', 'ó', 'ò', 'ǒ', 'ô'}
    for i in range(len(tokens)):
        if tokens[i]['type'] == 'V':
            val = tokens[i]['val']
            has_target_v = any(tv in val for tv in target_vowels)
            if has_target_v and 'i̯' in val and 'ː' not in val:
                # Find the next V token in the token list without crossing word boundaries (S) or pauses (P)
                next_v_idx = -1
                for k in range(i + 1, len(tokens)):
                    if tokens[k]['type'] == 'V':
                        next_v_idx = k
                        break
                    elif tokens[k]['type'] in {'C', 'P', 'S'}:
                        break
                
                if next_v_idx != -1:
                    tokens[i]['val'] = tokens[i]['val'].replace('i̯', 'j')
                    tokens[next_v_idx]['val'] = 'j' + tokens[next_v_idx]['val']

    # Step 4: Analyze word boundaries and clean up spaces
    # We iterate backwards so removing elements doesn't shift upcoming indices
    for i in range(len(tokens) - 1, -1, -1):
        if tokens[i]['type'] == 'S':
            # NEW: Keep space if it is directly adjacent to a Pause (| or ||)
            is_p_before = (i > 0 and tokens[i-1]['type'] == 'P')
            is_p_after = (i < len(tokens) - 1 and tokens[i+1]['type'] == 'P')
            
            if is_p_before or is_p_after:
                continue
            
            has_dot_boundary = False
            
            # Check left and right for a syllable boundary (DOT)
            if i > 0 and tokens[i-1]['type'] == 'DOT':
                has_dot_boundary = True
            if i < len(tokens) - 1 and tokens[i+1]['type'] == 'DOT':
                has_dot_boundary = True
                
            if has_dot_boundary:
                # Remove space if a dot is next to it
                tokens.pop(i)
            else:
                # If no dot, check if it's between a Consonant and a Vowel
                is_c_before = (i > 0 and tokens[i-1]['type'] == 'C')
                is_v_after = (i < len(tokens) - 1 and tokens[i+1]['type'] == 'V')
                
                if is_c_before and is_v_after:
                    tokens[i] = {'type': 'TIE', 'val': '‿'}
                else:
                    tokens.pop(i) # Otherwise, simply remove the space

    # Final Step: Reconstruct the string. By only joining t['val'], brackets are excluded.
    return "".join(t['val'] for t in tokens)

def process_text(input_filepath, output_filepath):
    print(f"Reading from {input_filepath}...")
    with open(input_filepath, 'r', encoding='utf-8') as f:
        raw_greek = f.read()

    print("Step 0.5: Preprocessing punctuation...")
    raw_greek = preprocess_punctuation(raw_greek)

    print("Step 1: Adding macrons/breves...")
    macronized_greek = macronizer.macronize(raw_greek)
    
    # Debug output: Save macronized text
    with open('output.txt', 'w', encoding='utf-8') as f:
        f.write(macronized_greek)

    prepared_text = macronized_greek.replace('^', '%').lower()

    print("Step 2: Converting to Beta Code...")
    beta_code_text = betacode.conv.uni_to_beta(prepared_text)
    beta_code_text = beta_code_text.replace('1', '')
    
    # Debug output: Save beta code text
    with open('output_betacode.txt', 'w', encoding='utf-8') as f:
        f.write(beta_code_text)

    print("Step 3: Converting Beta Code to IPA...")
    ipa_text = betacode_to_ipa(beta_code_text)
    
    # Convert punctuation dots and commas to pipes AFTER IPA generation[cite: 6]
    # This prevents the pipes from being swallowed up if they happen to exist in BETACODE_TO_IPA[cite: 6]
    ipa_text = ipa_text.replace(',', ' |').replace('.', ' ||')

    print("Step 4: Applying Syllabification and Cleaning Output...")
    final_text = apply_syllabification(ipa_text)

    with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write(final_text)

    print(f"\nSuccess! Saved to {output_filepath}")

# Run pipeline
process_text('input.txt', 'output_ipa.txt')