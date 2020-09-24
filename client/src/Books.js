import React, {useEffect, useState} from "react";
import _ from 'lodash'
import {spinner, SimplePopover} from "./utils";
import {
  Button,
  ButtonGroup,
  Nav,
  NavDropdown,
  Alert,
  Tabs,
  Tab,
  Card
} from "react-bootstrap";
import {FaTags, FaUser, FaThumbsUp, FaThumbsDown, FaCheck, FaTimes} from "react-icons/fa"

import { useSelector, useDispatch } from 'react-redux'
import { fetch_ } from './redux/actions'

function Books() {
  const [books, setBooks] = useState([])
  const [fetching, setFetching] = useState(false)
  const [notShared, setNotShared] = useState(false)
  const [shelf, setShelf] = useState('ai')  // like|dislike|already_read|remove|recommend

  const dispatch = useDispatch()
  const as = useSelector(state => state.as)
  const user = useSelector(state => state.user)

  const fetchShelf = async () => {
    setFetching(true)
    const {data, code, message} = await dispatch(fetch_(`books/${shelf}`, 'GET'))
    setFetching(false)
    if (code === 401) {return setNotShared(message)}
    setBooks(data)
  }

  useEffect(() => {
    fetchShelf()
  }, [shelf])

  if (notShared) {return <h5>{notShared}</h5>}

  const changeShelf = (shelf_) => {
    if (shelf === shelf_) {return}
    setShelf(shelf_)
  }

  const putOnShelf = async (id, shelf_) => {
    await dispatch(fetch_(`books/${id}/${shelf_}`, 'POST'))
    // _.remove(books, {id})
    setBooks(_.reject(books, {id}))
    // fetchBooks()
  }

  const ShelfButton = ({bid, shelf, icon, popover}) => (
    <SimplePopover text={popover}>
      <Button variant='outline-dark' onClick={() => putOnShelf(bid, shelf)}>
        {icon()}
      </Button>
    </SimplePopover>
  )

  const renderTabs = () => <>
    <Nav activeKey={shelf} onSelect={changeShelf}>
      <NavDropdown title="Shelves">
        <NavDropdown.Item eventKey="ai">AI Recommends</NavDropdown.Item>
        <NavDropdown.Item eventKey="like">Liked</NavDropdown.Item>
        <NavDropdown.Item eventKey="recommend">Therapist Recommends</NavDropdown.Item>
        <NavDropdown.Item eventKey="already_read">Already Read</NavDropdown.Item>
        <NavDropdown.Item eventKey="dislike">Disliked</NavDropdown.Item>
        <NavDropdown.Item eventKey="remove">Removed</NavDropdown.Item>
      </NavDropdown>
    </Nav>
    <br/>
  </>

  const renderBook = b => (
    <div key={b.id}>
      <h5>{b.title}</h5>
      <p>
        <FaUser /> {b.author}<br/>
        <FaTags /> {b.topic}</p>
      <p>{b.text}</p>
      <div>
        <ButtonGroup>
          {as ? <>
            <ShelfButton bid={b.id} shelf='recommend' icon={FaThumbsUp} popover="Recommend this book to the user (remove from results)" />
          </> : <>
            <ShelfButton bid={b.id} shelf='like' icon={FaThumbsUp} popover="Like and save for later (remove from results)" />
            <ShelfButton bid={b.id} shelf='dislike' icon={FaThumbsDown} popover="Dislike (remove from results)" />
            <ShelfButton bid={b.id} shelf='already_read' icon={FaCheck} popover="I've read this. Like but don't save (remove from results)" />
            <ShelfButton bid={b.id} shelf='remove' icon={FaTimes} popover="Remove from results, but don't affect algorithm." />
          </>}
        </ButtonGroup>
      </div>
      <hr />
    </div>
  )

  return <>
    <div>
      {renderTabs()}
      {fetching && spinner}
    </div>
    <div>
      {books.length > 0 ? <>
        <hr/>
        {!user.is_cool && <Alert variant='info'>Why no descriptions or ratings? I can't legally scrape Amazon or Goodreads, <a target="_blank" href="https://openlibrary.org/">Open Library</a> is great but doesn't have much data. <a href="mailto:tylerrenelle@gmail.com">Send me</a> suggestions!</Alert>}
        <Alert variant='info'>Wikipedia & other resources coming soon.</Alert>
        {books.map(renderBook)}
      </> : shelf === 'ai' ? <>
        <p>No AI recommendations yet. This will populate when you have enough entries.</p>
      </> : null}
    </div>
  </>
}

function Therapists() {
  const [therapists, setTherapists] = useState([])
  const dispatch = useDispatch()

  const fetchTherapists = async () => {
    const {data} = dispatch(fetch_('therapists'))
    setTherapists(data)
  }

  useEffect(() => {
    fetchTherapists()
  }, [])

  const renderTherapist = (t) => {
    let name = '';
    if (t.first_name) {name += t.first_name + ' '}
    if (t.last_name) {name += t.last_name + ' '}
    name += t.email
    return <Card>
      <Card.Body>
        <Card.Title>{name}</Card.Title>
        <Card.Text>{t.bio}</Card.Text>
      </Card.Body>
    </Card>
  }

  return <>
    <hr/>
    <Alert variant='info'>Therapists can mark their profile as "therapist", and their bio/specialties will be AI-matched to your entries. It's all done behind-the-scenes, they can't see anything of yours.</Alert>
    {therapists ? therapists.map(renderTherapist) : (
      <Alert variant='warning'>No therapist matches yet.</Alert>
    )}
  </>
}

export default function Resources() {
  return (
    <Tabs defaultActiveKey="books" id="uncontrolled-tab-example" variant="pills">
      <Tab eventKey="books" title="Books">
        <Books />
      </Tab>
      <Tab eventKey="therapists" title="Therapists">
        <Therapists />
      </Tab>
    </Tabs>
  )
}
