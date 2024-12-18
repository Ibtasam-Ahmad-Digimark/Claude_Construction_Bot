import os
import fitz  # PyMuPDF
import base64
import json
import requests
import time
import streamlit as st
from dotenv import load_dotenv
import anthropic
import tempfile  # Import tempfile for temporary directories

# Load environment variables from .env file
load_dotenv()
api_key = st.secrets["claude_api_key"]

# Initialize OpenAI client
client = anthropic.Anthropic(api_key=api_key)


first_query = """
Please review the provided construction plan document and prepare a comprehensive report that captures the square footage for the following materials and components, only give numarical values. Give the values that accuratly matches the provided context.:

1. Sheetrock 
2. Concrete 
3. Roofing 

For roofing, kindly break down the details for each subtype:
   - Shingle roofing
   - Modified bitumen
   - TPO (Thermoplastic Polyolefin)
   - Metal R panel
   - Standing seam

4. Structural steel

The construction plan may consist of multiple sections or phases. Please make sure the square footage calculations are thorough and include all relevant areas of the document. If there are multiple entries for any material, please combine them to present a total square footage.

Along with the square footage, it would be helpful to include a brief, thoughtful summary of the overall construction plan, highlighting key aspects such as:
   - Materials used
   - Phases of construction outlined
   - Any noteworthy specifications or design elements
   - Location


Ensure the report is detailed, accurate, and provides a complete overview of the square footage calculations and essential aspects of the construction plan.
"""

# Function to convert PDF to images
def pdf_to_images(uploaded_file, output_dir):
    pdf_document = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    for i in range(len(pdf_document)):
        page = pdf_document.load_page(i)
        pix = page.get_pixmap()
        img_path = os.path.join(output_dir, f'page_{i}.jpg')
        pix.save(img_path)
    pdf_document.close()

# Function to encode images to Base64
def encode_images(image_directory):
    encoded_images = []
    for filename in os.listdir(image_directory):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            image_path = os.path.join(image_directory, filename)
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
                encoded_images.append(encoded_image)
    return encoded_images



# Function to make chunked API requests and stream combined responses
def chunk_api_requests(encoded_images, user_query, client):
    responses = []  # This will store the responses for each image-query pair
    
    # Loop through each image and make a request to the API
    for i in range(0, len(encoded_images)):
        # time.sleep(1)  # Simulate a delay between requests

        # Create the message structure
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",  # Replace with the appropriate model name
            system="""
                    Analyze the construction plan (blueprints, plans, specs) for costs, timeline, phases, dimensions, materials, MEP details (HVAC, electrical, plumbing), drainage, erosion control, safety systems, and anything realted to construction. Don't tell anything other than this
                    """
            max_tokens=2048,
            messages=[  # Sending both the image and text content together
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",  # Specify the encoding type for the image
                                "media_type": "image/jpeg",  # Adjust the image format if necessary
                                "data": encoded_images[i],  # Image data
                            },
                        },
                        {
                            "type": "text",
                            "text": f"""
                            {user_query}
                            """  # The user query associated with the image
                        }
                    ],
                }
            ],
        )

        # Extract the response content
        try:
            # Assuming the message content is in the first element of the response
            response_content = message.content[0].text
            responses.append(response_content)
        except Exception as e:
            # If there is an error, append the error message
            print(f"Error: {str(e)}")
    
    # Combine all the responses into one string
    # combined_responses = "\n\n".join(responses)
    

    final_message = client.messages.create(
        model="claude-3-5-sonnet-20241022",  # Using the same model
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f'''Given the following user query and multiple responses, identify and combine the most relevant portions of the responses to provide a comprehensive and informative answer:

                **User Query:**
                {user_query}

                **Multiple Responses:**
                {responses}

                **Guidelines:**
                * Prioritize accuracy and relevance to the user's query.
                * Combine information from multiple responses if necessary.
                * Avoid redundancy and repetition.
                * Present the information in a clear and concise manner.

                **Output:**
                A single, coherent response that addresses the user's query effectively.
                '''
            }
        ]
    )

    # Print the final response
    return final_message.content[0].text

# Streamlit UI
st.title("PDF Chatbot")

uploaded_file = st.file_uploader("Upload a PDF.", type=["pdf"])

# Initialize session state to manage chat interaction
if 'responses' not in st.session_state:
    st.session_state.responses = []
if 'encoded_images' not in st.session_state:
    st.session_state.encoded_images = []
if 'current_query' not in st.session_state:
    st.session_state.current_query = ""
if 'is_first_query' not in st.session_state:
    st.session_state.is_first_query = True  # Track if it's the first query

# Chat interaction
if uploaded_file and api_key:
    # Only process the PDF if it hasn't been processed yet
    if not st.session_state.encoded_images:
        with tempfile.TemporaryDirectory() as temp_dir:
            RESULTS_PATH = temp_dir
            
            with st.spinner("Uploading PDF..."):
                # Convert uploaded PDF to images and encode only once
                pdf_to_images(uploaded_file, RESULTS_PATH)
                st.session_state.encoded_images = encode_images(RESULTS_PATH)
                

    for message in st.session_state.responses:
        with st.chat_message(message['role']):
            st.markdown(message['content'])

    # First predefined query logic
    if st.session_state.is_first_query:
        user_query = first_query
        st.session_state.current_query = user_query

        with st.spinner("Analyzing data..."):
            # Get the combined streamed response
            _f_response = chunk_api_requests(st.session_state.encoded_images, user_query, client)

        with st.chat_message('assistant'):
            st.markdown(_f_response)
        st.session_state.responses.append({"role": "assistant", "content": _f_response})

        st.session_state.is_first_query = False  # After processing the first query
        st.session_state.current_query = ""  # Clear current query after first completion

    # Display chat_input after first query
    if user_query:=st.chat_input("Enter your query:"):
        st.session_state.responses.append({"role": "user", "content": user_query})
        with st.spinner("Analyzing data..."):
            # Process user input and provide response
            response = chunk_api_requests(st.session_state.encoded_images, user_query, client)

        with st.chat_message('user'):
            st.markdown(user_query)

        with st.chat_message('assistant'):
            st.markdown(response)
        st.session_state.responses.append({"role": "assistant", "content": response})
else:
    st.warning("Please upload a PDF. Uploading PDF might take some time; don't close the application.")