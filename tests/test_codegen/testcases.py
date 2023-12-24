from __future__ import annotations

import contextlib
import re
import shutil
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import attrs
import graphql
import jinja2
from attr import Factory, define
from qtgqlcodegen.cli import app
from qtgqlcodegen.config import QtGqlConfig
from qtgqlcodegen.generator import SchemaGenerator
from qtgqlcodegen.types import CUSTOM_SCALARS, CustomScalarDefinition
from typer.testing import CliRunner

import tests.test_codegen.schemas as schemas
from tests.test_codegen.utils import temp_cwd

if TYPE_CHECKING:
    from strawberry import Schema

GENERATED_TESTS_DIR = Path(__file__).parent.parent / "gen"
if not GENERATED_TESTS_DIR.exists:
    GENERATED_TESTS_DIR.mkdir()
template_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(Path(__file__).parent / "templates_for_tests"),
    autoescape=jinja2.select_autoescape(),
    variable_start_string="👉",  # jinja uses {{ variable }}, using 👉 variable 👈 because C++ uses curly brackets.
    variable_end_string="👈",
)

TST_CMAKE_TEMPLATE = template_env.get_template("CMakeLists.jinja.txt")  # only build what you test.
TST_CONFIG_TEMPLATE = template_env.get_template("configtemplate.jinja.py")
TST_CATCH2_TEMPLATE = template_env.get_template("testcase.jinja.cpp")
CLI_RUNNER = CliRunner()


@define
class TstTemplateContext:
    config: QtGqlConfig
    url_suffix: str
    test_name: str


@define
class BoolWithReason:
    v: bool
    reason: str

    @classmethod
    def false(cls, reason: str) -> BoolWithReason:
        return cls(False, reason)

    @classmethod
    def true(cls, reason: str) -> BoolWithReason:
        return cls(True, reason)

    def __bool__(self):
        return self.v


class TestCaseMetadata(NamedTuple):
    should_test_updates: BoolWithReason = BoolWithReason.true("")
    should_test_deserialization: BoolWithReason = BoolWithReason.true("")


@define(slots=False, kw_only=True)
class QtGqlTestCase:
    operations: str
    schema: Schema
    test_name: str
    custom_scalars: dict = Factory(dict)
    qml_file: str = ""
    metadata: TestCaseMetadata = attrs.Factory(TestCaseMetadata)
    is_virtual_test: bool = False

    @cached_property
    def evaluator(self) -> SchemaGenerator:
        return SchemaGenerator(
            config=self.config,
            schema=graphql.build_schema(
                (self.graphql_dir / "schema.graphql").resolve(True).read_text("utf-8"),
            ),
        )

    @cached_property
    def test_dir(self) -> Path:
        ret = GENERATED_TESTS_DIR / self.test_name
        if not ret.exists():
            ret.mkdir()
        return ret

    @cached_property
    def graphql_dir(self) -> Path:
        ret = self.test_dir / "graphql"
        if not ret.exists():
            ret.mkdir()
        return ret

    @property
    def generated_dir(self):
        return self.config.generated_dir

    @cached_property
    def config_file(self) -> Path:
        return self.test_dir / "qtgqlconfig.py"

    @cached_property
    def schema_file(self) -> Path:
        return self.graphql_dir / "schema.graphql"

    @cached_property
    def operations_file(self) -> Path:
        return self.graphql_dir / "operations.graphql"

    @cached_property
    def testcase_file(self) -> Path:
        return self.test_dir / f"test_{self.test_name.lower()}.cpp"

    @cached_property
    def config(self) -> QtGqlConfig:
        return QtGqlConfig(
            graphql_dir=self.graphql_dir,
            env_name="default_env",
            custom_scalars=self.custom_scalars,
            generated_dir_name="../gen",
            qml_plugins_path="${CMAKE_BINARY_DIR}/tests",
        )

    @cached_property
    def url_suffix(self):
        return self.test_name

    @cached_property
    def custom_scalar_paths(self) -> list[Path]:
        """
        :return: list of user-defined custom scalars. this is needed in order to add them to the cmake target.
        """
        return [
            (self.generated_dir / cs.include_path).resolve(True)
            for cs in self.config.custom_scalars.values()
            if cs.graphql_name not in CUSTOM_SCALARS
        ]

    @contextlib.contextmanager
    def virtual_generate(self) -> None:
        """Generates and deletes after done."""
        assert self.is_virtual_test
        try:
            self.generate()
        finally:
            yield
            shutil.rmtree(self.test_dir)

    def generate(self) -> None:
        self.config.env_name = self.test_name
        template_context = TstTemplateContext(
            config=self.config,
            url_suffix=self.url_suffix,
            test_name=self.test_name,
        )
        self.schema_file.write_text(self.schema.as_str(), "UTF-8")
        self.operations_file.write_text(self.operations, "UTF-8")
        self.config_file.write_text(TST_CONFIG_TEMPLATE.render(context=template_context), "UTF-8")
        if not self.testcase_file.exists():
            self.testcase_file.write_text(
                TST_CATCH2_TEMPLATE.render(context=template_context),
                "UTF-8",
            )
        else:
            updated = re.sub(
                'auto ENV_NAME = std::string\\("([A-Za-z])*"\\)',
                f'auto ENV_NAME = std::string("{self.url_suffix}")',
                self.testcase_file.read_text("utf-8"),
            )
            self.testcase_file.write_text(updated, "UTF-8")

        with temp_cwd(self.config_file.parent):
            CLI_RUNNER.invoke(app, "gen", catch_exceptions=False)


RootScalarTestCase = QtGqlTestCase(
    schema=schemas.root_scalar.schema,
    operations="""
        query MainQuery {
            name
        }
    """,
    test_name="RootScalar",
)

ScalarsTestCase = QtGqlTestCase(
    schema=schemas.object_with_scalar.schema,
    operations="""
        query MainQuery {
          constUser {
            id
            name
            age
            agePoint
            male
            id
            uuid
            voidField
          }
        }
        query UserWithSameIDDiffFields {
          constUserWithModifiedFields {
            age
            agePoint
            id
            male
            name
            uuid
          }
        }
        """,
    test_name="Scalars",
)

SimpleGarbageCollection = QtGqlTestCase(
    schema=schemas.object_with_scalar.schema,
    operations="""
        query MainQuery {
          constUser {
            id
            name
            age
            agePoint
            male
            id
            uuid
            voidField
          }
        }
        """,
    test_name="GarbageCollection",
    metadata=TestCaseMetadata(
        should_test_updates=BoolWithReason.false("tested in scalar testcase"),
        should_test_deserialization=BoolWithReason.false("tested in scalar testcase"),
    ),
)

GqlOverHttpAsEnvTestCase = QtGqlTestCase(
    schema=schemas.object_with_scalar.schema,
    operations=ScalarsTestCase.operations,
    test_name="GqlOverHttpAsEnv",
    metadata=TestCaseMetadata(
        should_test_updates=BoolWithReason.false("tested in scalar testcase"),
        should_test_deserialization=BoolWithReason.false("tested in scalar testcase"),
    ),
)

OptionalScalarsTestCase = QtGqlTestCase(
    schema=schemas.object_with_optional_scalar.schema,
    operations="""
    query MainQuery($returnNone: Boolean! = false) {
      user(retNone: $returnNone) {
        name
        age
        agePoint
        uuid
        birth
      }
    }

    mutation FillUser($userId: ID!){
      fillUser(userId: $userId) {
        uuid
        name
        birth
        agePoint
        age
      }
    }
    mutation NullifyUser($userId: ID!){
      nullifyUser(userId: $userId) {
        uuid
        name
        birth
        agePoint
        age
      }
    }

    """,
    test_name="OptionalScalars",
)
NoIdOnQueryTestCase = QtGqlTestCase(
    # should append id to types that implements Node automatically.
    schema=schemas.object_with_scalar.schema,
    operations="""
    query MainQuery {
          user {
            name
            age
            agePoint
            male
          }
        }""",
    test_name="NoIdOnQuery",
    metadata=TestCaseMetadata(
        should_test_updates=BoolWithReason.false("nothing special here in that context"),
    ),
)

DateTimeTestCase = QtGqlTestCase(
    schema=schemas.object_with_datetime.schema,
    operations="""
       query MainQuery {
          user {
            name
            age
            birth
          }
        }
        mutation ChangeUserBirth($new_birth: DateTime!, $nodeId: ID!) {
          changeBirth(newBirth: $new_birth, nodeId: $nodeId) {
            age
            id
            birth
            name
          }
        }
        """,
    test_name="DateTime",
)

DecimalTestCase = QtGqlTestCase(
    schema=schemas.object_with_decimal.schema,
    operations="""
       query MainQuery {
          user {
            name
            age
            balance
          }
        }
        mutation UpdateBalance ($newBalance: Decimal!, $id: ID!){
          changeBalance(newBalance: $newBalance, nodeId: $id) {
            balance
          }
        }
    """,
    test_name="Decimal",
)
DateTestCase = QtGqlTestCase(
    schema=schemas.object_with_date.schema,
    operations="""
       query MainQuery {
          user {
            name
            age
            birth
          }
        }
        mutation ChangeUserBirth($new_birth: Date!, $nodeId: ID!) {
          changeBirth(newBirth: $new_birth, nodeId: $nodeId) {
            birth
          }
        }
        """,
    test_name="Date",
)
TimeScalarTestCase = QtGqlTestCase(
    schema=schemas.object_with_time_scalar.schema,
    operations="""
      query MainQuery {
          user {
            name
            age
            lunchTime
          }
        }
        mutation UpdateLunchTime ($newTime: Time!, $id: ID!) {
          changeLunchTime(newTime: $newTime, nodeId: $id) {
            lunchTime
          }
        }
        """,
    test_name="TimeScalar",
)

ScalarArgumentsTestCase = QtGqlTestCase(
    schema=schemas.scalar_arguments.schema,
    operations="""
    query MainQuery($i: Int!, $f: Float!, $string: String!, $b: Boolean!, $uuid: UUID!){
        getContainer(i: $i, f: $f, string: $string, b: $b, uuid: $uuid){
            string
            i
            f
            b
            uuid
        }
    }

    """,
    test_name="ScalarArguments",
)


OperationErrorTestCase = QtGqlTestCase(
    schema=schemas.operation_error.schema,
    operations="""
    query MainQuery {
        user{
            name
            age
        }
    }
    """,
    test_name="OperationError",
)

NestedObjectTestCase = QtGqlTestCase(
    schema=schemas.object_with_object.schema,
    operations="""
    query MainQuery {
        user{
            person{
                name
                age
            }
        }
    }

    mutation UpdateUserName($nodeId: ID!, $newName: String!) {
      changeName(newName: $newName, nodeId: $nodeId) {
        person {
          name
        }
      }
    }

    mutation ReplacePerson($nodeId: ID!){
    replacePerson(nodeId: $nodeId){
        person {
          name
        }
      }
    }
    """,
    test_name="NestedObject",
)
OptionalNestedObjectTestCase = QtGqlTestCase(
    schema=schemas.object_with_optional_object.schema,
    operations="""
    query MainQuery($return_null: Boolean!) {
      user(returnNull: $return_null) {
        person {
          name
          age
        }
      }
    }

    mutation UpdateUserName($nodeId: ID!, $newName: String!) {
      changeName(newName: $newName, nodeId: $nodeId) {
        person {
          name
        }
      }
    }
    """,
    test_name="OptionalNestedObject",
)
ObjectWithListOfObjectTestCase = QtGqlTestCase(
    schema=schemas.object_with_list_of_object.schema,
    operations="""
    query MainQuery {
        user{
            friends{
                name
                age
            }
        }
    }
    mutation AddFriend ($userId: ID!, $name: String!) {
    addFriend(userId: $userId, name: $name){
       friends{
            name
            age
            }
        }
    }
    """,
    test_name="ObjectWithListOfObject",
)


NonNodeInterfaceTestCase = QtGqlTestCase(
    schema=schemas.non_node_interface_field.schema,
    operations="""
    query AnimalQuery($kind: AnimalKind!) {
      animal(kind: $kind) {
        kind
        gender
        age
        id
        ... on Person {
          language
        }
        ... on Dog {
          furColor
        }
      }
    }

    mutation ChangeAgeMutation($id: ID!, $newAge: Int!) {
      changeAge(animalId: $id, newAge: $newAge) {
        age
        gender
        id
        ... on Person {
          language
        }
        ... on Dog {
          furColor
        }
        kind
      }
    }
    """,
    test_name="NonNodeInterface",
)


NodeInterfaceFieldTestCase = QtGqlTestCase(
    schema=schemas.node_interface_field.schema,
    operations="""
    query MainQuery ($ret: TypesEnum!) {
      node(ret: $ret) {
        id
        __typename
        ... on HasNameAgeInterface {
          name
          age
        }
        ... on User {
          password
        }
        ... on Dog {
          barks
        }
      }
    }

    mutation ChangeName($node_id: ID!, $new_name: String!){
        modifyName(nodeId: $node_id, newName: $new_name){
            ...on HasNameAgeInterface
            {
            name
            }
        }
    }
    """,
    test_name="NodeInterfaceField",
)

NonNodeUnionTestCase = QtGqlTestCase(
    schema=schemas.non_node_union.schema,
    operations="""
    query MainQuery($choice: UnionChoice!) {
        whoAmI(choice: $choice) {
          ... on Frog {
            name
            color
          }
          ... on Person {
            name
            age
          }
        }
      }
    """,
    test_name="NonNodeUnion",
)
NodeUnionTestCase = QtGqlTestCase(
    schema=schemas.node_union.schema,
    operations=NonNodeUnionTestCase.operations,
    test_name="NodeUnion",
)
EnumTestCase = QtGqlTestCase(
    schema=schemas.object_with_enum.schema,
    # __typename selection here has no value but to test durability.
    operations="""
        query MainQuery {
          user {
            __typename
            name
            age
            status
          }
        }

        mutation UpdateUserStatus($user_id: ID!, $status: Status!) {
            updateStatus(userId:$user_id, status: $status){
                status
            }
        }
        """,
    test_name="Enum",
)
RootEnumTestCase = QtGqlTestCase(
    schema=schemas.root_enum_schema.schema,
    operations="""
        query MainQuery {
          status
        }
        """,
    test_name="RootEnum",
)

ObjectsThatReferenceEachOtherTestCase = QtGqlTestCase(
    schema=schemas.object_reference_each_other.schema,
    test_name="ObjectsThatReferenceEachOther",
    operations="""
  query MainQuery {
      user {
        password
        person {
          name
          age
        }
      }
    }
""",
)

CountryScalar = CustomScalarDefinition(
    name="CountryScalar",
    graphql_name="Country",
    to_qt_type="QString",
    deserialized_type="QString",
    include_path="../countryscalar.hpp",
)

# A scalar that was implemented by a user.

CustomUserScalarTestCase = QtGqlTestCase(
    schema=schemas.object_with_user_defined_scalar.schema,
    custom_scalars={CountryScalar.graphql_name: CountryScalar},
    test_name="CustomUserScalar",
    operations="""
     query MainQuery {
          user {
            name
            age
            country
          }
        }
    """,
)

NonNodeTypeTestCase = QtGqlTestCase(
    schema=schemas.non_node_type.schema,
    operations="""
    query MainQuery {
        user{
            name
            age
        }
    }""",
    test_name="NonNodeType",
)

ListOfNonNodeType = QtGqlTestCase(
    schema=schemas.list_of_non_node.schema,
    operations="""
    query MainQuery {users{name}}

    mutation ChangeUserName($at: Int!, $name: String!) {
      modifyUser(at: $at, name: $name)
    }

    mutation InsertUser($at: Int!, $name: String!) {
      insertUser(at: $at, name: $name)
    }
    """,
    test_name="ListOfNonNodeType",
)

ListOfUnionTestCase = QtGqlTestCase(
    schema=schemas.list_of_union.schema,
    operations="""
    query MainQuery {
      randPerson {
        ...PersonFragment
      }
    }

    mutation RemoveAt($nodeId: ID!, $at: Int!) {
      removeAt(nodeId: $nodeId, at: $at) {
        ...PersonFragment
      }
    }

    mutation ModifyName($nodeId: ID!, $at: Int!, $name: String!) {
      modifyName(nodeId: $nodeId, at: $at, name: $name) {
        ...PersonFragment
      }
    }

    mutation InsertToList($nodeId: ID!, $at: Int!, $name: String!, $type: UnionTypes!) {
      insertToList(nodeId: $nodeId, at: $at, name: $name, type: $type) {
        ...PersonFragment
        }
      }
        """.replace(
        "...PersonFragment",
        """
        name
        pets {
          ... on Dog {
            name
            age
          }
          ... on Cat {
            name
            color
          }
        }
        """,
    ),
    test_name="ListOfUnion",
)

ListOfInterfaceTestcase = QtGqlTestCase(
    schema=schemas.list_of_interface.schema,
    operations=ListOfUnionTestCase.operations.replace("pets {", "pets { name"),
    test_name="ListOfInterface",
)

FragmentTestCase = QtGqlTestCase(
    schema=schemas.object_with_scalar.schema,
    operations="""
    fragment UserSelectionsFrag on User {
        name
        age
        agePoint
        male
        id
        uuid
        voidField
    }

    query MainQuery {
      constUser {
        ...UserSelectionsFrag
      }
    }

    query UserWithSameIDAndDifferentFieldsQuery {
      constUserWithModifiedFields {
        ...UserSelectionsFrag
      }
    }
    """,
    test_name="Fragment",
)

FragmentsOnInterfaceTestCase = QtGqlTestCase(
    schema=schemas.non_node_interface_field.schema,
    operations="""
    query AnimalQuery($kind: AnimalKind!) {
      animal(kind: $kind) {
        ...AnimalFragment
      }
    }

    mutation ChangeAgeMutation($id: ID!, $newAge: Int!) {
      changeAge(animalId: $id, newAge: $newAge) {
        ...AnimalFragment
      }
    }

    fragment AnimalFragment on AnimalInterface {
      kind
      gender
      age
      id
      ... on Person {
        language
      }
      ... on Dog {
        furColor
      }
    }
    """,
    test_name="FragmentsOnInterface",
)

FragmentWithOperationVariable = QtGqlTestCase(
    schema=schemas.object_with_optional_scalar.schema,
    operations="""
    fragment UserFragment on User {
        ...UserFragA
        ...UserFragB

    }
    fragment UserFragA on User{
      birth
      agePoint
      age
    }
    fragment UserFragB on User{
      uuid
      name
      id
    }

    mutation FillUser($userId: ID!){
      fillUser(userId: $userId) {
        ...UserFragment
      }
    }
    mutation NullifyUser($userId: ID!){
      nullifyUser(userId: $userId) {
        ...UserFragment
      }
    }


    fragment GetUserQuery on Query {
      user(retNone: $returnNone) {
        ...UserFragment
      }
    }

    query MainQuery($returnNone: Boolean! = false) {
      ...GetUserQuery
    }
    """,
    test_name="FragmentWithOperationVariable",
)

InputTypeOperationVariableTestCase = QtGqlTestCase(
    schema=schemas.input_type.schema,
    operations="""
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        header
        content
      }
    }

    mutation UpdatePostContent($input: ModifyPostContentInput!) {
      modifyPostContent(input_: $input) {
        content
      }
    }
    """,
    test_name="InputTypeOperationVariable",
)

OptionalInputTestCase = QtGqlTestCase(
    schema=schemas.optional_input_schema.schema,
    operations="""
    query HelloOrEchoQuery($echo: String){
      echoOrHello(echo: $echo)
    }
    """,
    test_name="OptionalInput",
)

RecursiveInputObjectTestCase = QtGqlTestCase(
    schema=schemas.recursive_input_object.schema,
    operations="""
    query MainQuery($inp: RecursiveInput!){
        depth(inp: $inp)
    }
    """,
    test_name="RecursiveInputObject",
    metadata=TestCaseMetadata(
        should_test_updates=BoolWithReason.false("input types are not cached ATM"),
    ),
)

CustomScalarInputTestCase = QtGqlTestCase(
    schema=schemas.custom_scalar_input_schema.schema,
    operations="""
        query ArgsQuery($decimal: Decimal!, $dt: DateTime!, $time: Time!, $date: Date!) {
          echoCustomScalar(decimal: $decimal, dt: $dt, time_: $time, date_: $date) {
            date_
            decimal
            dt
            time_
          }
        }

        query CustomScalarsInputObj($input: SupportedCustomScalarsInput!) {
          echoCustomScalarInputObj(input: $input) {
            dt
            decimal
            date_
            time_
          }
        }
    """,
    test_name="CustomScalarInput",
)

MutationOperationTestCase = QtGqlTestCase(
    schema=schemas.mutation_schema.schema,
    operations="""        query MainQuery {
          user {
            id
            name
            age
            agePoint
            male
            uuid
          }
        }""",
    test_name="MutationOperation",
)

SubscriptionTestCase = QtGqlTestCase(
    schema=schemas.subscription_schema.schema,
    operations="""
    subscription CountSubscription ($target: Int = 5){
        count(target: $target)
}
    """,
    test_name="Subscription",
)

QmlUsageTestCase = QtGqlTestCase(
    schema=schemas.qml_usage_test.schema,
    operations="""
    query SimpleQuery {
        simpleField
    }

    query FriendsListQuery($storeID: String!) {
        friends(storeId: $storeID){
            name
            age
        }
    }
    mutation RemoveFriend($storeID: String!, $friend_id: ID!) {
      removeFriend(storeId: $storeID, friendId: $friend_id)
    }
    mutation RemoveFriendsBatch($storeID: String!, $friends: [ID!]!) {
      removeFriends(storeId: $storeID, friends: $friends)
    }
    """,
    test_name="QmlUsage",
    metadata=TestCaseMetadata(
        should_test_updates=BoolWithReason.false("qml testcase"),
        should_test_deserialization=BoolWithReason.false("qml testcase"),
    ),
)

ListOfScalarTestCase = QtGqlTestCase(
    schema=schemas.list_of_scalar.schema,
    operations="""
    query GetRndPost{
      post{
        content
        tags
      }
    }

    mutation AddPostTag($postID: ID!, $tag: String!){
      addTag(postId: $postID, tag: $tag){
        content
        tags
      }
    }

    mutation RemovePostTag($postID: ID!, $at: Int!){
      removeTag(postId: $postID, at: $at){
        content
        tags
      }
    }

    mutation ReplacePostTag($postID: ID!, $at: Int!, $newTag: String!){
      replaceTag(postId: $postID, at: $at, newTag: $newTag){
        content
        tags
      }
    }
    """,
    test_name="ListOfScalar",
)
ListOfScalarArgumentTestCase = QtGqlTestCase(
    schema=schemas.list_of_scalar_argument.schema,
    operations="""
    query EchoArg($what: [String!]!){
      echo(what: $what)
    }
    """,
    test_name="ListOfScalarArgument",
    metadata=TestCaseMetadata(
        should_test_updates=BoolWithReason.false("input types are not cached ATM"),
    ),
)

ListOfScalarInInputObjectTestCase = QtGqlTestCase(
    schema=schemas.list_of_scalar_in_input_object.schema,
    operations="""
    query EchoArg($what: What!){
      echo(what: $what)
    }
    """,
    test_name="ListOfScalarInInputObject",
    metadata=TestCaseMetadata(
        should_test_updates=BoolWithReason.false("input types are not cached ATM"),
    ),
)

ListOfInputObjectTestCase = QtGqlTestCase(
    schema=schemas.list_of_input_object.schema,
    operations="""
    query MainQuery($what: What!){
      echo(what: $what)
    }
    """,
    test_name="ListOfInputObject",
    metadata=TestCaseMetadata(
        should_test_updates=BoolWithReason.false("input types are not cached ATM"),
    ),
)

ObjectInInterface = QtGqlTestCase(
    schema=schemas.interface_with_object_field.schema,
    operations="""
    query Animal($kind: AnimalKind!) {
      animal(kind: $kind) {
        metadata{
          kind
            gender
            age
        }
        id
        ... on Person {
          language
        }
        ... on Dog {
          furColor
        }
      }
    }    """,
    test_name="ObjectInInterface",
    metadata=TestCaseMetadata(
        should_test_updates=BoolWithReason.false(
            "There is no reason it would fail, this only failed due to object types being generated after interfaces.",
        ),
    ),
)

PartiallyInitializedNode = QtGqlTestCase(
    schema=schemas.partially_initialized_node.schema,
    operations="""
    query PartialCreateUser{
      createUser{
            name
            age
        }
    }

    query GetUserById($user_id: ID!) {
      getUserById(userId: $user_id) {
        name
        age
        agePoint
        uuid
        birth
      }
    }
    """,
    test_name="PartiallyInitializedNode",
    metadata=TestCaseMetadata(
        should_test_updates=BoolWithReason.false("resolves issue #381"),
        should_test_deserialization=BoolWithReason.false("resolves issue #381"),
    ),
)
all_test_cases = [
    ScalarsTestCase,
    SimpleGarbageCollection,
    GqlOverHttpAsEnvTestCase,
    OptionalScalarsTestCase,
    NoIdOnQueryTestCase,
    DateTimeTestCase,
    DateTestCase,
    TimeScalarTestCase,
    DecimalTestCase,
    NestedObjectTestCase,
    OptionalNestedObjectTestCase,
    ObjectWithListOfObjectTestCase,
    ScalarArgumentsTestCase,
    EnumTestCase,
    RootScalarTestCase,
    NonNodeTypeTestCase,
    InputTypeOperationVariableTestCase,
    NonNodeInterfaceTestCase,
    NodeInterfaceFieldTestCase,
    NonNodeUnionTestCase,
    ListOfNonNodeType,
    ListOfUnionTestCase,
    ListOfInterfaceTestcase,
    FragmentTestCase,
    FragmentsOnInterfaceTestCase,
    FragmentWithOperationVariable,
    NodeUnionTestCase,
    QmlUsageTestCase,
    ListOfScalarTestCase,
    ListOfScalarArgumentTestCase,
    ListOfScalarInInputObjectTestCase,
    ListOfInputObjectTestCase,
    OptionalInputTestCase,
    RecursiveInputObjectTestCase,
    ObjectInInterface,
    CustomUserScalarTestCase,
    ObjectsThatReferenceEachOtherTestCase,
]

implemented_testcases = [
    ScalarsTestCase,
    SimpleGarbageCollection,
    GqlOverHttpAsEnvTestCase,
    NoIdOnQueryTestCase,
    DateTimeTestCase,
    DecimalTestCase,
    DateTestCase,
    TimeScalarTestCase,
    OptionalScalarsTestCase,
    NestedObjectTestCase,
    OptionalNestedObjectTestCase,
    ObjectWithListOfObjectTestCase,
    EnumTestCase,
    NonNodeInterfaceTestCase,
    ScalarArgumentsTestCase,
    RootScalarTestCase,
    NonNodeTypeTestCase,
    InputTypeOperationVariableTestCase,
    NodeInterfaceFieldTestCase,
    NonNodeUnionTestCase,
    ListOfNonNodeType,
    ListOfUnionTestCase,
    ListOfInterfaceTestcase,
    FragmentTestCase,
    FragmentsOnInterfaceTestCase,
    FragmentWithOperationVariable,
    NodeUnionTestCase,
    QmlUsageTestCase,
    ListOfScalarTestCase,
    ListOfScalarArgumentTestCase,
    ListOfScalarInInputObjectTestCase,
    ListOfInputObjectTestCase,
    OptionalInputTestCase,
    RecursiveInputObjectTestCase,
    ObjectInInterface,
    PartiallyInitializedNode,
    CustomUserScalarTestCase,
]


def generate_testcases(*testcases: QtGqlTestCase) -> None:
    (GENERATED_TESTS_DIR / "CMakeLists.txt").write_text(
        TST_CMAKE_TEMPLATE.render(context={"testcases": testcases}),
        "UTF-8",
    )
    for tc in testcases:
        tc.generate()


if __name__ == "__main__":
    generate_testcases(
        SimpleGarbageCollection,
        GqlOverHttpAsEnvTestCase,
        NoIdOnQueryTestCase,
        DateTimeTestCase,
        DecimalTestCase,
        DateTestCase,
        TimeScalarTestCase,
        OptionalScalarsTestCase,
    )
